from collections import deque, namedtuple
from enum import Enum
from pathlib import Path
from random import randrange
from typing import Deque, List

import pygame
import pygame_menu


GameLog = namedtuple('GameLog', 'snake_direction, snake_parts, food')
GameArea = namedtuple('GameArea', 'left, top, width, height')


class Snake:
    PART_SIZE = 15

    class Direction(Enum):
        UP = (0, -1)
        DOWN = (0, 1)
        LEFT = (-1, 0)
        RIGHT = (1, 0)

    parts: List[pygame.Rect]

    def __init__(self, start_x: int, start_y: int, tail_length: int = 0):
        self.direction = self.Direction.LEFT
        self.parts = [pygame.Rect(start_x, start_y, self.PART_SIZE, self.PART_SIZE)]
        for _ in range(tail_length):
            self.increase()

    def has_collisions(self, game_are: GameArea) -> bool:
        head = self.head
        return (
                head.left < game_are.left
                or head.right > game_are.left + game_are.width
                or head.top < game_are.top
                or head.bottom > game_are.top + game_are.height
                or any(head.colliderect(part) for part in self.tail)
        )

    def increase(self) -> None:
        part = self.parts[-1]
        size = self.PART_SIZE
        new_part = pygame.Rect(part.left, part.top, size, size)
        self.parts.append(new_part)

    def move(self) -> None:
        for i in range(len(self.tail), 0, -1):
            previous_part = self.parts[i - 1]
            current_part = self.parts[i]
            current_part.x = previous_part.x
            current_part.y = previous_part.y

        x_dir, y_dir = self.direction.value
        head = self.head
        head.move_ip(x_dir * head.width, y_dir * head.height)

    def turn_up(self) -> None:
        if self.direction != self.Direction.DOWN:
            self.direction = self.Direction.UP

    def turn_down(self) -> None:
        if self.direction != self.Direction.UP:
            self.direction = self.Direction.DOWN

    def turn_left(self) -> None:
        if self.direction != self.Direction.RIGHT:
            self.direction = self.Direction.LEFT

    def turn_right(self) -> None:
        if self.direction != self.Direction.LEFT:
            self.direction = self.Direction.RIGHT

    @property
    def head(self) -> pygame.Rect:
        return self.parts[0]

    @property
    def tail(self) -> List[pygame.Rect]:
        return self.parts[1:]


class GameSession:
    LOG_LIMIT = 25
    FOOD_SIZE = 20
    SNAKE_START_LENGTH = 3

    REVERT_SOUND_ID = 5
    FOOD_SOUND_ID = 6
    FAIL_SOUND_ID = 7

    logs: Deque[GameLog]

    def __init__(self, game_area: GameArea, frame_time: int, is_predictable_future: bool):
        self.area = game_area
        self._frame_time = frame_time  # in milliseconds

        self.is_running = True
        self.logs = deque(maxlen=self.LOG_LIMIT)
        self.is_reversed = False
        self._last_full_revert = pygame.time.get_ticks()
        self._is_predictable_future = is_predictable_future
        self._next_foods = []

        start_left = game_area.left + ((game_area.width / 2) // Snake.PART_SIZE) * Snake.PART_SIZE
        start_top = game_area.top + ((game_area.height / 2) // Snake.PART_SIZE) * Snake.PART_SIZE
        self.snake = Snake(start_x=start_left, start_y=start_top, tail_length=self.SNAKE_START_LENGTH - 1)
        self.food = self.generate_food()

        sounds_directory = Path(__file__).parent / 'sounds'
        self._reverse_sound = pygame.mixer.Sound(str(sounds_directory / 'tape_rewind.ogg'))
        self._food_sound = pygame.mixer.Sound(str(sounds_directory / 'profit.wav'))
        self._fail_sound = pygame.mixer.Sound(str(sounds_directory / 'fail.wav'))

    def move_snake(self) -> None:
        pressed_keys = pygame.key.get_pressed()
        self.is_reversed = pressed_keys[pygame.K_r] and self.logs and not self.is_full_reversed
        sound_channel = pygame.mixer.Channel(self.REVERT_SOUND_ID)
        if self.is_reversed:
            self._move_backward()
            if not sound_channel.get_busy():
                sound_channel.play(self._reverse_sound)
        else:
            self._reverse_sound.stop()
            if sound_channel.get_busy():
                sound_channel.stop()
            self._move_forward()

    def handle_keypress(self, key: int) -> None:
        snake = self.snake
        handlers = {
            pygame.K_UP: snake.turn_up,
            pygame.K_DOWN: snake.turn_down,
            pygame.K_LEFT: snake.turn_left,
            pygame.K_RIGHT: snake.turn_right,
        }
        handler = handlers.get(key)
        if handler:
            handler()

    def generate_food(self) -> pygame.Rect:
        size = self.FOOD_SIZE
        area = self.area
        if self._is_predictable_future and self._next_foods:
            return self._next_foods.pop()

        rand_left = randrange(area.left, area.left + area.width - (size * 2))
        rand_top = randrange(area.top, area.top + area.height - (size * 2))
        return pygame.Rect(rand_left, rand_top, size, size)

    @property
    def is_full_reversed(self) -> bool:
        """
        Designates if time could be turned back more, after complete usage of the power.

        Is used to prevent turning back time when charge is close to zero.
        """
        return pygame.time.get_ticks() - self._last_full_revert <= (self.LOG_LIMIT * self._frame_time)

    @property
    def score(self) -> int:
        return len(self.snake.parts) - self.SNAKE_START_LENGTH

    @property
    def reverse_percent(self) -> int:
        return round((len(self.logs) / self.LOG_LIMIT) * 100)

    def _move_forward(self) -> None:
        snake = self.snake
        snake.move()

        self.is_running = not snake.has_collisions(game_are=self.area)

        if not self.is_running:  # game over
            sound_channel = pygame.mixer.Channel(self.FAIL_SOUND_ID)
            if not sound_channel.get_busy():
                sound_channel.play(self._fail_sound)

        if self.is_running and snake.head.colliderect(self.food):  # snake eats a food
            snake.increase()
            self.food = self.generate_food()
            sound_channel = pygame.mixer.Channel(self.FOOD_SOUND_ID)
            if not sound_channel.get_busy():
                sound_channel.play(self._food_sound)

        self._add_log()

    def _move_backward(self) -> None:
        last_log = self.logs.pop()
        if not self.logs:  # turning back is completely used
            self._last_full_revert = pygame.time.get_ticks()

        self.snake.direction = last_log.snake_direction
        self.snake.parts = [
            pygame.Rect(left, top, Snake.PART_SIZE, Snake.PART_SIZE) for left, top in last_log.snake_parts
        ]

        food = pygame.Rect(last_log.food[0], last_log.food[1], self.FOOD_SIZE, self.FOOD_SIZE)
        if self._is_predictable_future and food.center != self.food.center:
            self._next_foods.append(self.food)
        self.food = food

    def _add_log(self) -> None:
        snake = self.snake
        self.logs.append(
            GameLog(
                snake_direction=snake.direction,
                snake_parts=tuple((part.left, part.top) for part in snake.parts),
                food=(self.food.left, self.food.top),
            )
        )


class GameDifficulty(Enum):
    """The value means time of one game frame, used to setup game speed."""

    EASY = 80
    NORMAL = 40
    HARD = 20


class Game:
    BORDER_WIDTH, BORDER_HEIGHT = 800, 600
    BAR_SIZE = (Snake.PART_SIZE * 3) - 7

    def __init__(self, screen: pygame.Surface):
        self._screen = screen
        self._score_font = pygame.font.Font(pygame.font.match_font('arial'), 18)
        self._game_over_font = pygame.font.Font(pygame.font.match_font('arial'), 48)
        self._frame_time = GameDifficulty.NORMAL.value
        self._is_predictable_future = False

    def set_difficulty(self, __, difficulty: GameDifficulty) -> None:
        self._frame_time = difficulty.value

    def set_destiny(self, __, is_destiny: bool) -> None:
        self._is_predictable_future = is_destiny

    def run(self) -> None:
        game_area = GameArea(left=0, top=self.BAR_SIZE, width=self.BORDER_WIDTH, height=self.BORDER_HEIGHT)
        game = GameSession(
            game_area=game_area,
            frame_time=self._frame_time,
            is_predictable_future=self._is_predictable_future,
        )
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN and not game.is_running:  # go back to menu after game over
                        return

                    game.handle_keypress(event.key)

            pygame.time.delay(self._frame_time)
            if game.is_running:
                game.move_snake()
                self._render_game_session(game)
            else:
                self._render_game_over()
            pygame.display.flip()

    def _render_game_session(self, game: GameSession) -> None:
        screen = self._screen
        if game.is_reversed:
            background_color = "white"
            snake_head_color = "purple"
            snake_tail_color = "red"
            food_color = "blue"

            bar_bg_color = "black"
            reverse_bar_color = "green"
            text_color = (255, 255, 255)
        else:
            background_color = "black"
            snake_head_color = "orange"
            snake_tail_color = "green"
            food_color = "yellow"

            bar_bg_color = "white"
            reverse_bar_color = "red"
            text_color = (0, 0, 0)

        # draw background:
        screen.fill(background_color)

        # draw snake:
        pygame.draw.rect(screen, snake_head_color, game.snake.head)
        for part in game.snake.tail:
            pygame.draw.rect(screen, snake_tail_color, part)

        # draw food:
        pygame.draw.rect(screen, food_color, game.food)

        # draw bar section:
        pygame.draw.rect(screen, bar_bg_color, (0, 0, self.BORDER_WIDTH, self.BAR_SIZE), 0)
        bar_left, bar_top = 25, 7
        bar_height = 20
        bar_border_size = 4
        pygame.draw.rect(
            screen,
            "grey",
            (bar_left, bar_top, 100 + bar_border_size, bar_height + bar_border_size),
            bar_border_size - 1,
        )
        pygame.draw.rect(
            screen,
            "grey" if game.is_full_reversed else reverse_bar_color,
            (bar_left + (bar_border_size / 2), bar_top + (bar_border_size / 2), game.reverse_percent, bar_height),
        )

        score_surface = self._score_font.render(f'Score: {game.score}', True, text_color)
        score_rect = score_surface.get_rect()
        score_rect.midtop = self.BORDER_WIDTH - 100, 10
        screen.blit(score_surface, score_rect)

    def _render_game_over(self) -> None:
        text_surface = self._game_over_font.render(f'GAME OVER', True, (255, 0, 0))
        text_rect = text_surface.get_rect()
        text_rect.midtop = (self.BORDER_WIDTH // 2), ((self.BORDER_HEIGHT + self.BAR_SIZE) // 2) - 18
        self._screen.blit(text_surface, text_rect)
        help_surface = self._score_font.render('Press ENTER to go back to menu.', True, (255, 0, 0))
        help_rect = help_surface.get_rect()
        help_rect.midtop = (text_rect.x + 140, text_rect.y + 60)
        self._screen.blit(help_surface, help_rect)

    @staticmethod
    def _exit():
        pygame.quit()
        exit(0)


def main():
    pygame.init()
    pygame.display.set_caption("Snake of Time")
    screen = pygame.display.set_mode((Game.BORDER_WIDTH, Game.BORDER_HEIGHT + Game.BAR_SIZE))
    game = Game(screen=screen)

    menu = pygame_menu.Menu(
        height=Game.BORDER_HEIGHT + Game.BAR_SIZE, width=Game.BORDER_WIDTH,
        title='Snake of Time', theme=pygame_menu.themes.THEME_DARK,
    )

    control_help_text = (
        "R - turn back time (if you have enough charge) | "
        "Arrow buttons - control snake movement"
    )

    menu.add_label("Control buttons:", max_char=-1, font_size=21)
    menu.add_label(control_help_text, max_char=-1, font_size=16)
    menu.add_label('', max_char=0)
    menu.add_selector(
        'Change difficulty:',
        items=[
            ('Easy', GameDifficulty.EASY),
            ('Normal', GameDifficulty.NORMAL),
            ('Hard', GameDifficulty.HARD),
        ],
        default=1, onchange=game.set_difficulty, font_size=21,
    )
    menu.add_selector(
        'Predictable future:',
        items=[
            ('Yes', True),
            ('No', False),
        ],
        default=1, onchange=game.set_destiny, font_size=21,
    )

    menu.add_button('PLAY', game.run)
    menu.add_button('EXIT', pygame_menu.events.EXIT)

    menu.mainloop(screen)


if __name__ == '__main__':
    main()
