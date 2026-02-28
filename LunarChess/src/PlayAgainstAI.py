import pygame
import sys
import math
import random
import time
import threading
import copy

pygame.init()

WIDTH, HEIGHT = 700, 820
GRID_SIZE = 3
CELL = 160
MARGIN_X = (WIDTH - GRID_SIZE * CELL) // 2
MARGIN_Y = 140
FPS = 60

BG_DEEP     = (5, 8, 30)
GLOW_GRID   = (180, 220, 255)

FROST_CORE  = (160, 210, 255)
FROST_GLOW  = (80,  160, 255)
FROST_OUTER = (40,  90,  200)

IRID_CORE   = (255, 80,  90)
IRID_GLOW   = (200, 30,  60)
IRID_OUTER  = (120, 10,  30)

FADE_DUR    = 0.35
MCTS_SIMS   = 5000


class GameState:
    def __init__(self):
        self.board   = [[0]*GRID_SIZE for _ in range(GRID_SIZE)]
        self.queues  = {1: [], 2: []}
        self.current = 1
        self.winner  = 0

    def clone(self):
        gs = GameState()
        gs.board   = [row[:] for row in self.board]
        gs.queues  = {1: list(self.queues[1]), 2: list(self.queues[2])}
        gs.current = self.current
        gs.winner  = self.winner
        return gs

    def legal_moves(self):
        if self.winner:
            return []
        return [(r, c) for r in range(GRID_SIZE)
                for c in range(GRID_SIZE) if self.board[r][c] == 0]

    def apply(self, move):
        r, c = move
        q = self.queues[self.current]
        if len(q) == 3:
            old_r, old_c = q.pop(0)
            self.board[old_r][old_c] = 0
        q.append((r, c))
        self.board[r][c] = self.current
        if self._check_win(self.current):
            self.winner = self.current
        else:
            self.current = 3 - self.current

    def _check_win(self, player):
        b = self.board
        for i in range(3):
            if all(b[i][c] == player for c in range(3)):
                return True
            if all(b[r][i] == player for r in range(3)):
                return True
        if all(b[i][i] == player for i in range(3)):
            return True
        if all(b[i][2-i] == player for i in range(3)):
            return True
        return False

    def is_terminal(self):
        return self.winner != 0

    def to_key(self):
        return (
            tuple(tuple(row) for row in self.board),
            tuple(self.queues[1]),
            tuple(self.queues[2]),
            self.current
        )


def minimax(state, depth, alpha, beta, maximizing, ai_player):
    if state.is_terminal():
        return (1.0 if state.winner == ai_player else -1.0), None
    moves = state.legal_moves()
    if not moves or depth == 0:
        return 0.0, None
    best_move = moves[0]
    if maximizing:
        val = -999.0
        for m in moves:
            s2 = state.clone()
            s2.apply(m)
            score, _ = minimax(s2, depth - 1, alpha, beta, False, ai_player)
            if score > val:
                val = score
                best_move = m
            alpha = max(alpha, val)
            if beta <= alpha:
                break
        return val, best_move
    else:
        val = 999.0
        for m in moves:
            s2 = state.clone()
            s2.apply(m)
            score, _ = minimax(s2, depth - 1, alpha, beta, True, ai_player)
            if score < val:
                val = score
                best_move = m
            beta = min(beta, val)
            if beta <= alpha:
                break
        return val, best_move


def _urgent_move(st, player):
    for move in st.legal_moves():
        tmp = st.clone()
        tmp.apply(move)
        if tmp.winner == player:
            return move
    return None


def _order_moves(st, moves):
    urgent_win   = _urgent_move(st, st.current)
    urgent_block = _urgent_move(st, 3 - st.current)
    priority = []
    normal   = []
    for m in moves:
        if m == urgent_win or m == urgent_block:
            priority.append(m)
        else:
            normal.append(m)
    random.shuffle(normal)
    return priority + normal


class MCTSNode:
    def __init__(self, state, parent=None, move=None):
        self.state    = state
        self.parent   = parent
        self.move     = move
        self.children = []
        self.wins     = 0.0
        self.visits   = 0
        raw           = state.legal_moves()
        self.untried  = _order_moves(state, raw)

    def is_fully_expanded(self):
        return len(self.untried) == 0

    def best_child(self, c=1.1):
        return max(
            self.children,
            key=lambda n: (n.wins / n.visits) + c * math.sqrt(
                math.log(self.visits) / n.visits)
        )

    def expand(self):
        move        = self.untried.pop(0)
        child_state = self.state.clone()
        child_state.apply(move)
        child = MCTSNode(child_state, parent=self, move=move)
        self.children.append(child)
        return child

    def rollout(self, ai_player):
        st    = self.state.clone()
        depth = 0
        while not st.is_terminal() and depth < 50:
            moves = st.legal_moves()
            if not moves:
                break
            win_move   = _urgent_move(st, st.current)
            block_move = _urgent_move(st, 3 - st.current)
            if win_move:
                st.apply(win_move)
            elif block_move:
                st.apply(block_move)
            else:
                st.apply(random.choice(moves))
            depth += 1
        return st.winner

    def backprop(self, result, ai_player, perspective):
        self.visits += 1
        if result == 0:
            self.wins += 0.1
        elif result == perspective:
            self.wins += 1.0
        else:
            self.wins += 0.0
        if self.parent:
            self.parent.backprop(result, ai_player, 3 - perspective)


def mcts_search(state, n_sims, ai_player):
    empty_cells = sum(1 for r in range(GRID_SIZE)
                      for c in range(GRID_SIZE) if state.board[r][c] == 0)
    if empty_cells <= 5:
        _, move = minimax(state, depth=8, alpha=-999.0, beta=999.0,
                          maximizing=True, ai_player=ai_player)
        if move:
            return move

    root = MCTSNode(state.clone())
    for _ in range(n_sims):
        node = root
        while node.is_fully_expanded() and node.children:
            node = node.best_child()
        if not node.state.is_terminal():
            if not node.is_fully_expanded():
                node = node.expand()
        result = node.rollout(ai_player)
        node.backprop(result, ai_player, node.state.current)
    if not root.children:
        moves = state.legal_moves()
        win = _urgent_move(state, ai_player)
        blk = _urgent_move(state, 3 - ai_player)
        return win or blk or random.choice(moves)
    return max(root.children, key=lambda n: n.visits).move


def draw_glowing_circle(surface, cx, cy, r, core_col, glow_col, outer_col, alpha=255):
    for rad, col, a_mul in [
        (r + 18, outer_col, 0.18),
        (r + 10, glow_col,  0.30),
        (r +  4, glow_col,  0.55),
        (r,      core_col,  1.00),
    ]:
        a = int(alpha * a_mul)
        surf = pygame.Surface((rad*2+2, rad*2+2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*col, a), (rad+1, rad+1), rad)
        surface.blit(surf, (cx - rad - 1, cy - rad - 1))
    hi_surf = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
    pygame.draw.ellipse(hi_surf, (255, 255, 255, int(alpha * 0.55)),
                        (r//3, r//5, r//2, r//3))
    surface.blit(hi_surf, (cx - r, cy - r))


def draw_sun_orb(surface, cx, cy, r, core_col, glow_col, outer_col, alpha=255, t=0):
    num_rays = 8
    ray_len_long  = int(r * 0.60)
    ray_len_short = int(r * 0.38)
    ray_surf = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
    spin = t * 0.4
    for i in range(num_rays * 2):
        angle = (math.pi / num_rays) * i + spin
        ray_len = ray_len_long if i % 2 == 0 else ray_len_short
        ray_w   = 4 if i % 2 == 0 else 2
        x1 = cx + math.cos(angle) * (r + 6)
        y1 = cy + math.sin(angle) * (r + 6)
        x2 = cx + math.cos(angle) * (r + 6 + ray_len)
        y2 = cy + math.sin(angle) * (r + 6 + ray_len)
        a_ray = int(alpha * 0.50)
        pygame.draw.line(ray_surf, (*glow_col, a_ray), (int(x1), int(y1)), (int(x2), int(y2)), ray_w)
    surface.blit(ray_surf, (0, 0))
    draw_glowing_circle(surface, cx, cy, r, core_col, glow_col, outer_col, alpha)


def draw_frost_moon(surface, cx, cy, r, alpha=255, t=0):
    draw_sun_orb(surface, cx, cy, r, FROST_CORE, FROST_GLOW, FROST_OUTER, alpha, t)


def draw_irid_moon(surface, cx, cy, r, alpha=255, t=0):
    draw_sun_orb(surface, cx, cy, r, IRID_CORE, IRID_GLOW, IRID_OUTER, alpha, t)


class Particle:
    def __init__(self, x, y, col):
        self.x = x + random.uniform(-8, 8)
        self.y = y + random.uniform(-8, 8)
        angle = random.uniform(0, math.tau)
        speed = random.uniform(1.5, 4.5)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.col = col
        self.life = 1.0
        self.decay = random.uniform(0.025, 0.055)
        self.size = random.uniform(2, 5)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.05
        self.life -= self.decay

    def draw(self, surf):
        if self.life <= 0:
            return
        a = int(self.life * 255)
        s = pygame.Surface((int(self.size*2)+2, int(self.size*2)+2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.col, a),
                           (int(self.size)+1, int(self.size)+1), int(self.size))
        surf.blit(s, (int(self.x - self.size), int(self.y - self.size)))


STARS = [(random.randint(0, WIDTH), random.randint(0, HEIGHT),
          random.uniform(0.3, 1.2), random.uniform(0, math.tau))
         for _ in range(120)]


def draw_background(surface, t):
    surface.fill(BG_DEEP)
    for i in range(4):
        nb = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        r = 180 + i*40
        cx = WIDTH//2 + math.sin(t*0.2 + i) * 60
        cy = HEIGHT//2 + math.cos(t*0.15 + i) * 40
        pygame.draw.circle(nb, (20+i*8, 30+i*10, 80+i*15, 18), (int(cx), int(cy)), r)
        surface.blit(nb, (0, 0))
    for sx, sy, brightness, phase in STARS:
        twinkle = 0.5 + 0.5 * math.sin(t * 1.8 + phase)
        a = min(255, int(brightness * twinkle * 200 + 55))
        r = 1 if brightness < 0.7 else 2
        s = pygame.Surface((r*2+2, r*2+2), pygame.SRCALPHA)
        pygame.draw.circle(s, (200, 220, 255, a), (r+1, r+1), r)
        surface.blit(s, (sx - r, sy - r))


class Piece:
    def __init__(self, player, row, col, cx, cy):
        self.player   = player
        self.row      = row
        self.col      = col
        self.cx       = cx
        self.cy       = cy
        self.birth    = time.time()
        self.fade_in  = True
        self.fade_out = False
        self.alpha    = 0
        self.alive    = True

    def start_fade_out(self):
        self.fade_out  = True
        self.fade_in   = False
        self.fade_start = time.time()

    def update(self):
        now = time.time()
        age = now - self.birth
        if self.fade_in:
            self.alpha = min(255, int((age / FADE_DUR) * 255))
            if age >= FADE_DUR:
                self.fade_in = False
                self.alpha   = 255
        if self.fade_out:
            elapsed    = now - self.fade_start
            self.alpha = max(0, int(255 - (elapsed / FADE_DUR) * 255))
            if elapsed >= FADE_DUR:
                self.alive = False

    def draw(self, surface, is_oldest):
        alpha = self.alpha
        r = 46
        if is_oldest and not self.fade_out:
            pulse = 0.65 + 0.2 * math.sin(time.time() * 6)
            alpha = int(alpha * pulse)
        if self.player == 1:
            draw_frost_moon(surface, self.cx, self.cy, r, alpha, time.time())
        else:
            draw_irid_moon(surface, self.cx, self.cy, r, alpha, time.time())


class LunarChess:
    AI_PLAYER = 2

    def __init__(self):
        self.screen     = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("LunarChess")
        self.clock      = pygame.time.Clock()
        self.font_title = pygame.font.SysFont("Georgia", 36, bold=True)
        self.font_sub   = pygame.font.SysFont("Georgia", 20)
        self.font_info  = pygame.font.SysFont("Courier New", 16)
        self.font_small = pygame.font.SysFont("Courier New", 13)
        self.reset()

    def reset(self):
        self.board      = [[0]*GRID_SIZE for _ in range(GRID_SIZE)]
        self.pieces     = []
        self.queues     = {1: [], 2: []}
        self.current    = 1
        self.particles  = []
        self.winner     = 0
        self.game_over  = False
        self.hover_cell = None
        self.win_line   = None
        self.game_state = GameState()
        self.ai_thinking = False
        self.ai_move     = None
        self.ai_thread   = None
        self.think_start = None

    def cell_center(self, row, col):
        cx = MARGIN_X + col * CELL + CELL // 2
        cy = MARGIN_Y + row * CELL + CELL // 2
        return cx, cy

    def get_cell(self, mx, my):
        col = (mx - MARGIN_X) // CELL
        row = (my - MARGIN_Y) // CELL
        if 0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE:
            px = mx - MARGIN_X - col * CELL
            py = my - MARGIN_Y - row * CELL
            if 0 <= px <= CELL and 0 <= py <= CELL:
                return row, col
        return None

    def place(self, row, col):
        if self.board[row][col] != 0:
            return
        q = self.queues[self.current]
        if len(q) == 3:
            oldest = q.pop(0)
            self.board[oldest.row][oldest.col] = 0
            oldest.start_fade_out()
            col_p = FROST_GLOW if oldest.player == 1 else IRID_GLOW
            for _ in range(22):
                self.particles.append(Particle(oldest.cx, oldest.cy, col_p))

        cx, cy = self.cell_center(row, col)
        p = Piece(self.current, row, col, cx, cy)
        self.pieces.append(p)
        q.append(p)
        self.board[row][col] = self.current

        col_p = FROST_CORE if self.current == 1 else IRID_CORE
        for _ in range(14):
            self.particles.append(Particle(cx, cy, col_p))

        self.game_state.apply((row, col))

        win, line = self.check_win(self.current)
        if win:
            self.winner  = self.current
            self.game_over = True
            self.win_line  = line
            wc = FROST_CORE if self.current == 1 else IRID_CORE
            wx, wy = self.cell_center(line[0][0], line[0][1])
            for _ in range(50):
                self.particles.append(Particle(
                    wx + random.randint(-80, 80),
                    wy + random.randint(-80, 80), wc))
        else:
            self.current = 3 - self.current
            if self.current == self.AI_PLAYER and not self.game_over:
                self.trigger_ai()

    def trigger_ai(self):
        self.ai_thinking = True
        self.think_start = time.time()
        state_copy = self.game_state.clone()
        def worker():
            move = mcts_search(state_copy, MCTS_SIMS, self.AI_PLAYER)
            self.ai_move = move
        self.ai_thread = threading.Thread(target=worker, daemon=True)
        self.ai_thread.start()

    def check_win(self, player):
        b = self.board
        lines = []
        for i in range(3):
            lines.append([(i,0),(i,1),(i,2)])
            lines.append([(0,i),(1,i),(2,i)])
        lines.append([(0,0),(1,1),(2,2)])
        lines.append([(0,2),(1,1),(2,0)])
        for line in lines:
            if all(b[r][c] == player for r,c in line):
                return True, line
        return False, None

    def draw_grid(self, t):
        for r in range(GRID_SIZE + 1):
            y = MARGIN_Y + r * CELL
            alpha_line = 100 + int(40 * math.sin(t + r))
            s = pygame.Surface((GRID_SIZE * CELL, 2), pygame.SRCALPHA)
            s.fill((*GLOW_GRID, alpha_line))
            self.screen.blit(s, (MARGIN_X, y))
        for c in range(GRID_SIZE + 1):
            x = MARGIN_X + c * CELL
            alpha_line = 100 + int(40 * math.sin(t * 1.1 + c))
            s = pygame.Surface((2, GRID_SIZE * CELL), pygame.SRCALPHA)
            s.fill((*GLOW_GRID, alpha_line))
            self.screen.blit(s, (x, MARGIN_Y))

    def draw_hover(self, t):
        if self.hover_cell and not self.game_over and self.current != self.AI_PLAYER:
            row, col = self.hover_cell
            if self.board[row][col] == 0:
                cx, cy = self.cell_center(row, col)
                pulse = 0.4 + 0.25 * math.sin(t * 4)
                a = int(pulse * 255)
                col_p = FROST_GLOW if self.current == 1 else IRID_GLOW
                s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                s.fill((*col_p, int(a * 0.15)))
                self.screen.blit(s, (MARGIN_X + col*CELL, MARGIN_Y + row*CELL))
                r = 38
                if self.current == 1:
                    draw_frost_moon(self.screen, cx, cy, r, a // 2, t)
                else:
                    draw_irid_moon(self.screen, cx, cy, r, a // 2, t)

    def draw_win_line(self, t):
        if not self.win_line:
            return
        r1, c1 = self.win_line[0]
        r2, c2 = self.win_line[-1]
        x1, y1 = self.cell_center(r1, c1)
        x2, y2 = self.cell_center(r2, c2)
        pulse = 0.6 + 0.4 * math.sin(t * 5)
        a = int(pulse * 255)
        col = FROST_GLOW if self.winner == 1 else IRID_GLOW
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.line(s, (*col, a), (x1, y1), (x2, y2), 5)
        self.screen.blit(s, (0, 0))

    def draw_thinking(self, t):
        elapsed = time.time() - self.think_start
        dots    = "." * (int(elapsed * 2.5) % 4)
        label   = self.font_sub.render(f"Iridescent Moon is thinking{dots}", True, IRID_GLOW)
        self.screen.blit(label, (WIDTH//2 - label.get_width()//2, 98))

        orb_cx = WIDTH//2
        orb_cy = 118
        for i in range(5):
            angle = t * 2.5 + (math.tau / 5) * i
            ox = orb_cx + math.cos(angle) * 28
            oy = orb_cy + math.sin(angle) * 10
            a  = int(180 + 60 * math.sin(t * 3 + i))
            draw_irid_moon(self.screen, int(ox), int(oy), 7, a, t)

    def draw_ui(self, t):
        title_col = (160 + int(40*math.sin(t)), 200, 255)
        title = self.font_title.render("*  LunarChess  *", True, title_col)
        self.screen.blit(title, (WIDTH//2 - title.get_width()//2, 24))

        if not self.game_over:
            if self.ai_thinking:
                self.draw_thinking(t)
            else:
                p_name = "Frost Moon" if self.current == 1 else "Iridescent Moon"
                p_col  = FROST_GLOW if self.current == 1 else IRID_GLOW
                pulse  = 0.75 + 0.25 * math.sin(t * 3.5)
                p_col  = tuple(int(c * pulse) for c in p_col)
                label  = self.font_sub.render(f"{p_name}'s Turn", True, p_col)
                self.screen.blit(label, (WIDTH//2 - label.get_width()//2, 88))
        else:
            w_name = "Frost Moon" if self.winner == 1 else "Iridescent Moon"
            w_col  = FROST_CORE if self.winner == 1 else IRID_CORE
            glow   = 0.7 + 0.3 * math.sin(t * 4)
            w_col  = tuple(min(255, int(c * glow + 30)) for c in w_col)
            msg    = self.font_title.render(f"* {w_name} Wins! *", True, w_col)
            self.screen.blit(msg, (WIDTH//2 - msg.get_width()//2, 78))
            hint   = self.font_info.render("Press R to restart", True, (140, 170, 220))
            self.screen.blit(hint, (WIDTH//2 - hint.get_width()//2, HEIGHT - 44))

        for player, q in self.queues.items():
            base_x = 40 if player == 1 else WIDTH - 40
            for i, piece in enumerate(q):
                dx = i * 22 * (1 if player == 1 else -1)
                px = base_x + dx
                py = HEIGHT - 30
                r  = 7
                col = FROST_GLOW if player == 1 else IRID_GLOW
                a   = 220 if piece != (q[0] if q else None) else \
                      int(110 + 80*math.sin(t*6))
                s = pygame.Surface((r*2+2, r*2+2), pygame.SRCALPHA)
                pygame.draw.circle(s, (*col, a), (r+1, r+1), r)
                self.screen.blit(s, (px - r, py - r))

        frost_label = self.font_info.render("  Frost Moon (You)", True, FROST_GLOW)
        irid_label  = self.font_info.render("  Iridescent Moon (AI)", True, IRID_GLOW)
        self.screen.blit(frost_label, (18, HEIGHT - 70))
        self.screen.blit(irid_label,  (18, HEIGHT - 48))
        draw_frost_moon(self.screen, 14, HEIGHT - 62, 10, 200, 0)
        draw_irid_moon(self.screen,  14, HEIGHT - 40, 10, 200, 0)

        sims_label = self.font_small.render(f"MCTS sims: {MCTS_SIMS}", True, (80, 100, 160))
        self.screen.blit(sims_label, (WIDTH - sims_label.get_width() - 10, HEIGHT - 20))

    def run(self):
        t = 0.0
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            t += dt

            if self.ai_thinking and self.ai_move is not None:
                self.ai_thinking = False
                move = self.ai_move
                self.ai_move = None
                self.place(*move)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        self.reset()
                if event.type == pygame.MOUSEMOTION:
                    self.hover_cell = self.get_cell(*event.pos)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if not self.game_over and not self.ai_thinking:
                        if self.current != self.AI_PLAYER:
                            cell = self.get_cell(*event.pos)
                            if cell:
                                self.place(*cell)

            for p in self.pieces:
                p.update()
            self.pieces = [p for p in self.pieces if p.alive or p.fade_in or
                           (p.fade_out and p.alpha > 0)]

            for p in self.particles:
                p.update()
            self.particles = [p for p in self.particles if p.life > 0]

            draw_background(self.screen, t)
            self.draw_grid(t)
            self.draw_hover(t)

            oldest = {1: self.queues[1][0] if len(self.queues[1]) == 3 else None,
                      2: self.queues[2][0] if len(self.queues[2]) == 3 else None}

            for piece in self.pieces:
                is_old = (oldest[piece.player] is piece)
                piece.draw(self.screen, is_old)

            for p in self.particles:
                p.draw(self.screen)

            if self.game_over:
                self.draw_win_line(t)

            self.draw_ui(t)
            pygame.display.flip()


if __name__ == "__main__":
    LunarChess().run()