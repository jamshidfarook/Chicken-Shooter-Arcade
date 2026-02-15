import random, math
from io import BytesIO
from PIL import Image as PILImage

from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.graphics import Rectangle, Color
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel

# --- Window setup ---
WIDTH, HEIGHT = Window.width, Window.height
Window.title = "Chicken Shooter Arcade"

# --- Scale images ---
def scale_image(path, target_width=None, target_height=None):
    pil_img = PILImage.open(path)
    w, h = pil_img.size

    if target_width and target_height:
        ratio = min(target_width / w, target_height / h)
    elif target_width:
        ratio = target_width / w
    elif target_height:
        ratio = target_height / h
    else:
        ratio = 1

    new_size = (int(w * ratio), int(h * ratio))
    pil_img = pil_img.resize(new_size, PILImage.Resampling.LANCZOS)
    data = BytesIO()
    pil_img.save(data, format='png')
    data.seek(0)
    return CoreImage(data, ext='png')

# --- Load images ---
ground_img = scale_image("images/ground.png", target_width=WIDTH)
ground_height = ground_img.height
ground_y = 0  # bottom

chicken_img = scale_image("images/chicken.png", target_height=int(HEIGHT * 0.13))
chicken_width, chicken_height = chicken_img.width, chicken_img.height
chicken_large = scale_image("images/chicken.png", target_height=int(HEIGHT * 0.25))

fried_chicken_small = scale_image("images/fried_chicken.png", target_height=int(HEIGHT * 0.13))
fried_chicken_large = scale_image("images/fried_chicken.png", target_height=int(HEIGHT * 0.25))

# --- Load GIF frames ---
gif_path = "images/bg.gif"
gif = PILImage.open(gif_path)
bg_frames = []
try:
    while True:
        frame = gif.copy().convert("RGBA").resize((WIDTH, HEIGHT), PILImage.Resampling.LANCZOS)
        data = BytesIO()
        frame.save(data, format='png')
        data.seek(0)
        bg_frames.append(CoreImage(data, ext='png'))
        gif.seek(gif.tell() + 1)
except EOFError:
    pass
bg_frame_count = len(bg_frames)

# --- Sounds ---
jump_sound = SoundLoader.load("sounds/jump.wav")
hit_sound = SoundLoader.load("sounds/hit.wav")
failed_sound = SoundLoader.load("sounds/failed.wav")

# --- Music playlists ---
menu_music = [f"sounds/menu{i}.mp3" for i in range(1,4)]
game_music = [f"sounds/game{i}.mp3" for i in range(1,11)]

# --- Music Manager ---
class MusicManager:
    def __init__(self):
        self.current_music = None
        self.current_index = -1
        self.playlist = []
        self.volume = 0.5
        self.state = None  # None, "menu" or "game"

    def set_volume(self, vol):
        self.volume = max(0.0, min(vol, 1.0))
        if self.current_music:
            self.current_music.volume = self.volume

    def play_next(self, playlist=None):
        if playlist:
            self.playlist = playlist
        if not self.playlist:
            return

        # Pick a random next song, avoid repeating the current
        next_index = self.current_index
        attempts = 0
        while next_index == self.current_index and attempts < 10:
            next_index = random.randint(0, len(self.playlist)-1)
            attempts += 1
        self.current_index = next_index

        # Stop previous song and unbind callback
        if self.current_music:
            self.current_music.unbind(on_stop=self._on_music_stop)
            self.current_music.stop()

        # Load new song
        self.current_music = SoundLoader.load(self.playlist[self.current_index])
        if self.current_music:
            self.current_music.volume = self.volume
            self.current_music.bind(on_stop=self._on_music_stop)
            self.current_music.play()

    def _on_music_stop(self, *args):
        if self.playlist:
            self.play_next()

    def switch_state(self, new_state):
        """Stop current music and switch playlists safely."""
        if self.state != new_state:
            self.state = new_state
            # Stop current music first (Extra safeguard)
            if self.current_music:
                self.current_music.unbind(on_stop=self._on_music_stop)
                self.current_music.stop()
                self.current_music = None

            # Start the new playlist
            if self.state == "menu":
                self.play_next(menu_music)
            elif self.state == "game":
                self.play_next(game_music)

sfx_volume = 0.5
music_volume = 0.5

def set_sfx_volume(vol):
    global sfx_volume
    sfx_volume = max(0.0, min(vol,1.0))
    if jump_sound: jump_sound.volume = 0.6*sfx_volume
    if hit_sound: hit_sound.volume = 1.2*sfx_volume
    if failed_sound: failed_sound.volume = 1.1*sfx_volume

# --- Chicken creation ---
def new_chicken(score):
    base_y = 0
    min_jump = int(HEIGHT * 0.317)
    max_jump = int(HEIGHT * 0.733)
    jump_height = random.randint(min_jump, max_jump)

    base_speed = 0.05 + score * 0.001
    speed_variation = random.uniform(-0.005, 0.01)
    jump_speed = max(base_speed + speed_variation, 0.01)

    base_fall = 5 + score * 0.1
    fall_variation = random.uniform(-0.5, 1)
    fall_speed = max(base_fall + fall_variation, 1)

    horizontal_speed = random.uniform(-0.7, 0.7)

    # NEW: small horizontal drift
    horizontal_speed = random.uniform(-0.7 - score*0.0005, 0.7 + score*0.0005)

    return {
        "x": random.randint(0, WIDTH - chicken_width),
        "vx": horizontal_speed,   # NEW
        "base_y": base_y,
        "jump_progress": 0,
        "max_jump": jump_height,
        "jump_speed": jump_speed,
        "fall_speed": fall_speed,
        "state": "jumping",
        "shot": False,
        "hit_time": None,
        "jump_sound_played": False,
        "current_y": base_y
    }

def reset_game(game):
    game.score = 0
    game.misses = 0
    game.spawn_timer = 0
    game.chickens = [new_chicken(0)]
    game.miss_sound_played = False

# --- Main Game Widget ---
class GameWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bg_index = 0
        self.bg_timer = 0
        self.chickens = [new_chicken(0)]
        self.spawn_timer = 0
        self.max_chickens_base = 5
        self.max_misses = 100
        self.score = 0
        self.misses = 0
        self.miss_sound_played = False
        self.game_state = "loading"
        self.music_manager = MusicManager()
        self.music_manager.set_volume(0.5)  
        self.music_manager.switch_state("menu")
        # --- Home menu chicken interaction ---
        self.home_chicken_pos = (WIDTH//2 - chicken_width//2, int(HEIGHT * 0.25))
        self.home_chicken_hold_time = 0
        self.home_chicken_holding = False
        self.home_chicken_cooked = False
        self.home_chicken_cook_timer = 0
        Clock.schedule_interval(self.update, 1/30)
        self.difficulty_levels = ["Easy", "Medium", "Hard"]
        self.current_difficulty_index = 1  # Medium
        self.current_difficulty = self.difficulty_levels[self.current_difficulty_index]
        self.sfx_volume = sfx_volume  # 0.5 by default
        self.music_volume = music_volume  # 0.5 by default
        # Slider positions (will update dynamically)
        self.sfx_slider_pos = (WIDTH//2 - int(WIDTH*0.25)//2, HEIGHT//2 + int(HEIGHT*0.08))
        self.music_slider_pos = (WIDTH//2 - int(WIDTH*0.25)//2, HEIGHT//2 - int(HEIGHT*0.02))
        self.slider_width = int(WIDTH * 0.25)
        self.slider_height = int(HEIGHT * 0.03)
        self.active_slider = None  # None, "sfx" or "music"
        self.about_texts = [
            "Chicken Shooter Arcade",
            "Made by Jamshid Farook",
            "© 2026 All Rights Reserved"
        ]
        self.about_positions = []  
        self.about_speed = 50

        # --- Loading screen variables ---
        self.loading_progress = 0
        self.loading_steps = [
            self.load_images,
            self.fake_step,
            self.load_sounds,
            self.fake_step,
            self.finish_loading
        ]
        self.current_loading_step = 0
        Clock.schedule_interval(self.run_loading_step, 0.15)

    def run_loading_step(self, dt):
        if self.current_loading_step < len(self.loading_steps):
            self.loading_steps[self.current_loading_step]()
            self.current_loading_step += 1
            self.loading_progress = self.current_loading_step / len(self.loading_steps)
        else:
            Clock.unschedule(self.run_loading_step)

    def load_images(self):
        print("Images Loaded")

    def fake_step(self):
        pass

    def load_sounds(self):
        print("Sounds Loaded")

    def finish_loading(self):
        print("Loading Finished")
        Clock.schedule_once(lambda dt: setattr(self, "game_state", "home"), 0.4)

    def on_touch_down(self, touch):
        x, y = touch.pos

        if self.game_state == "paused":
            x, y = touch.pos

            # --- Pause menu sliders ---
            # Music slider
            mx, my = self.music_slider_pos
            if mx <= x <= mx + self.slider_width and my <= y <= my + self.slider_height:
                self.active_slider = "music"
                self.update_slider(x)
                return

            # SFX slider
            sx, sy = self.sfx_slider_pos
            if sx <= x <= sx + self.slider_width and sy <= y <= sy + self.slider_height:
                self.active_slider = "sfx"
                self.update_slider(x)
                return

            # --- Buttons ---
            # Resume
            x0, y0 = self.resume_button_pos
            w, h = self.resume_button_size
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                self.game_state = "playing"
                return

            # Exit to Home
            x0, y0 = self.exit_button_pos
            w, h = self.exit_button_size
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                reset_game(self)
                self.game_state = "home"
                return

        # --- Home screen buttons ---
        if self.game_state == "home":
            # Start Game button
            x0, y0 = self.start_button_pos
            w, h = self.start_button_size
            if (x0 <= x <= x0 + w and y0 <= y <= y0 + h):
                reset_game(self)
                self.game_state = "playing"
                return
            
            # --- Settings button (replaces Difficulty) ---
            x0, y0 = self.settings_button_pos
            w, h = self.settings_button_size
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                self.game_state = "settings"  # switch to the settings menu
                return

            # About button
            x0, y0 = self.about_button_pos
            w, h = self.about_button_size
            if (x0 <= x <= x0 + w and y0 <= y <= y0 + h):
                self.game_state = "about"
                return
            
            # --- Chicken press detection ---
            cx, cy = self.home_chicken_pos
            img = fried_chicken_large

            if cx <= x <= cx + img.width and cy <= y <= cy + img.height:
                self.home_chicken_holding = True
                self.home_chicken_hold_time = 0

        if self.game_state == "about":
            x0, y0 = self.back_button_pos
            w, h = self.back_button_size
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                self.game_state = "home"
                return

        if self.game_state == "gameover":
            x0, y0 = self.retry_button_pos
            w, h = self.retry_button_size
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                reset_game(self)
                self.game_state = "playing"
                return
            
            # Game Over Difficulty button
            x0, y0 = self.diff_button_pos
            w, h = self.diff_button_size
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                self.current_difficulty_index = (self.current_difficulty_index + 1) % len(self.difficulty_levels)
                self.current_difficulty = self.difficulty_levels[self.current_difficulty_index]
                return

            x0, y0 = self.home_button_pos
            w, h = self.home_button_size
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                reset_game(self)
                self.game_state = "home"
                self.home_chicken_cooked = False
                self.home_chicken_hold_time = 0
                self.home_chicken_cook_timer = 0
                return
            
        # --- Settings menu clicks ---
        if self.game_state == "settings":
            x, y = touch.pos

            # --- Difficulty button ---
            x0, y0 = self.diff_button_pos
            w, h = self.diff_button_size
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                # Cycle difficulty
                self.current_difficulty_index = (self.current_difficulty_index + 1) % len(self.difficulty_levels)
                self.current_difficulty = self.difficulty_levels[self.current_difficulty_index]
                return

            # --- Back button ---
            x0, y0 = self.back_button_pos
            w, h = self.back_button_size
            if x0 <= x <= x0 + w and y0 <= y <= y0 + h:
                # Return to Home menu
                self.game_state = "home"
                return

            # --- SFX Slider ---
            sx, sy = self.sfx_slider_pos
            if sx <= x <= sx + self.slider_width and sy <= y <= sy + self.slider_height:
                self.active_slider = "sfx"
                self.update_slider(x)
                return

            # --- Music Slider ---
            mx, my = self.music_slider_pos
            if mx <= x <= mx + self.slider_width and my <= y <= my + self.slider_height:
                self.active_slider = "music"
                self.update_slider(x)
                return

        # --- Gameplay clicks ---
        if self.game_state == "playing" and y > int(HEIGHT * 0.083):  # avoids touching ground
            
            # Check if Pause button was clicked
            if hasattr(self, 'pause_button_pos'):
                x0, y0 = self.pause_button_pos
                button_width = int(WIDTH * 0.15)
                button_height = int(HEIGHT * 0.08)
                if x0 <= x <= x0 + button_width and y0 <= y <= y0 + button_height:
                    self.game_state = "paused"  # Switch to paused state
                    return  # Stop processing other touches while pausing

            for chicken in self.chickens:
                chicken_top = chicken["current_y"] + chicken_height
                chicken_bottom = chicken["current_y"]
                if chicken["x"] <= x <= chicken["x"] + chicken_width and chicken_bottom <= y <= chicken_top:
                    chicken["shot"] = True
                    chicken["state"] = "hit"
                    if hit_sound: hit_sound.play()
                    self.score += 1
            
    def on_touch_up(self, touch):
        self.active_slider = None
        
        if self.game_state == "home":
            self.home_chicken_holding = False
            self.home_chicken_hold_time = 0

    def on_touch_move(self, touch):
        # Only update slider if currently dragging
        if hasattr(self, 'active_slider') and self.active_slider:
            self.update_slider(touch.x)

    def update(self, dt):

        if self.game_state == "loading":
                self.canvas.clear()
                with self.canvas:
                    Color(0, 0, 0, 1)
                    Rectangle(pos=(0, 0), size=(WIDTH, HEIGHT))

                    label = CoreLabel(
                        text=f"Loading... {int(self.loading_progress*100)}%",
                        font_size=int(HEIGHT * 0.06),
                        color=(1, 1, 1, 1)
                    )
                    label.refresh()
                    Rectangle(
                        texture=label.texture,
                        pos=(WIDTH//2 - label.texture.size[0]//2, HEIGHT//2 + 40),
                        size=label.texture.size
                    )

                    bar_width = int(WIDTH * 0.6)
                    bar_height = 30
                    bar_x = WIDTH//2 - bar_width//2
                    bar_y = HEIGHT//2 - 20

                    Color(0.3, 0.3, 0.3, 1)
                    Rectangle(pos=(bar_x, bar_y), size=(bar_width, bar_height))

                    Color(0.2, 0.8, 0.2, 1)
                    Rectangle(
                        pos=(bar_x, bar_y),
                        size=(bar_width * self.loading_progress, bar_height)
                    )

                return

        # --- Call once per frame, but switch music only if state changed ---
        if not hasattr(self, 'last_game_state') or self.last_game_state != self.game_state:
            if self.game_state in ["home", "about", "settings"]:
                self.music_manager.switch_state("menu")
            elif self.game_state == "playing":
                self.music_manager.switch_state("game")
            self.last_game_state = self.game_state

        # --- Update background frame ---
        self.bg_timer += dt
        # --- Home chicken hold logic ---
        if self.game_state == "home":

            if self.home_chicken_holding:
                self.home_chicken_hold_time += dt

                if self.home_chicken_hold_time >= 5 and not self.home_chicken_cooked:
                    self.home_chicken_cooked = True
                    self.home_chicken_cook_timer = 0
                    if hit_sound:
                        hit_sound.play()

            if self.home_chicken_cooked:
                self.home_chicken_cook_timer += dt
                if self.home_chicken_cook_timer >= 3:
                    self.home_chicken_cooked = False
                    self.home_chicken_hold_time = 0

        if self.bg_timer >= 1/10:
            self.bg_index = (self.bg_index + 1) % bg_frame_count
            self.bg_timer = 0

        self.spawn_timer += dt

        # --- Clear canvas for redrawing ---
        self.canvas.clear()
        with self.canvas:
            # --- Draw background ---
            bg_frame = bg_frames[self.bg_index]
            scale_ratio = HEIGHT / bg_frame.height  # fills HEIGHT
            new_bg_width = int(bg_frame.width * scale_ratio)
            bg_x = (WIDTH - new_bg_width) // 2  # center horizontally
            Rectangle(texture=bg_frame.texture, pos=(bg_x, 0), size=(new_bg_width, HEIGHT))

            # --- Handle Home / About / Game Over screens ---
            if self.game_state in ["home", "about", "gameover"]:
                # Draw ground at bottom
                Rectangle(texture=ground_img.texture, pos=(0, 0), size=(WIDTH, ground_img.height))

                if self.game_state == "home":
                    # Title
                    title_font_size = int(HEIGHT * 0.08)
                    title = CoreLabel(text="Chicken Shooter Arcade", font_size=title_font_size, color=(1,0,0,1))
                    title.refresh()
                    Rectangle(texture=title.texture,
                            pos=(WIDTH//2 - title.texture.size[0]//2, HEIGHT - 170),
                            size=title.texture.size)
                    # --- Home menu chicken ---
                    img = fried_chicken_large if self.home_chicken_cooked else chicken_large
                    chicken_x = WIDTH//2 - img.width//2
                    chicken_y = HEIGHT//2 + int(HEIGHT * 0.02)

                    self.home_chicken_pos = (chicken_x, chicken_y)

                    Rectangle(
                        texture=img.texture,
                        pos=self.home_chicken_pos,
                        size=(img.width, img.height)
                    )

                    # Buttons
                    # Button size
                    button_width = int(WIDTH * 0.2)
                    button_height = int(HEIGHT * 0.1)
                    button_spacing = int(HEIGHT * 0.02)  # space between buttons

                    # Home menu buttons
                    # Start Game button (keep as is)
                    self.start_button_pos = (WIDTH//2 - button_width//2, HEIGHT//2 - int(HEIGHT*0.10))
                    self.start_button_size = (button_width, button_height)

                    # Settings button (instead of Difficulty)
                    self.settings_button_pos = (WIDTH//2 - button_width//2,
                                                self.start_button_pos[1] - button_height - button_spacing)
                    self.settings_button_size = (button_width, button_height)

                    # About button below Settings
                    self.about_button_pos = (WIDTH//2 - button_width//2,
                                            self.settings_button_pos[1] - button_height - button_spacing)
                    self.about_button_size = (button_width, button_height)

                    # Draw rectangles for buttons
                    Color(0.2, 0.6, 0.8, 1)
                    Rectangle(pos=self.start_button_pos, size=self.start_button_size)
                    Rectangle(pos=self.settings_button_pos, size=self.settings_button_size)  # ✅ fixed
                    Rectangle(pos=self.about_button_pos, size=self.about_button_size)

                    # Button text
                    button_font_size = int(HEIGHT * 0.04)
                    Color(1,1,1,1)

                    # Start Game text
                    start_label = CoreLabel(text="Start Game", font_size=button_font_size)
                    start_label.refresh()
                    Rectangle(
                        texture=start_label.texture,
                        pos=(self.start_button_pos[0] + button_width//2 - start_label.texture.size[0]//2,
                            self.start_button_pos[1] + button_height//2 - start_label.texture.size[1]//2),
                        size=start_label.texture.size
                    )

                    # Settings button text
                    settings_label = CoreLabel(text="Settings", font_size=button_font_size)  # ✅ fixed
                    settings_label.refresh()
                    Rectangle(
                        texture=settings_label.texture,
                        pos=(self.settings_button_pos[0] + button_width//2 - settings_label.texture.size[0]//2,
                            self.settings_button_pos[1] + button_height//2 - settings_label.texture.size[1]//2),
                        size=settings_label.texture.size
                    )

                    # About text
                    about_label = CoreLabel(text="About", font_size=button_font_size)
                    about_label.refresh()
                    Rectangle(
                        texture=about_label.texture,
                        pos=(self.about_button_pos[0] + button_width//2 - about_label.texture.size[0]//2,
                            self.about_button_pos[1] + button_height//2 - about_label.texture.size[1]//2),
                        size=about_label.texture.size
                    )

                if self.game_state == "about":
                    # Draw background & ground
                    Rectangle(texture=ground_img.texture, pos=(0, 0), size=(WIDTH, ground_img.height))
                    
                    # --- About Text (black, bold, lower on screen) ---
                    start_y = HEIGHT * 0.65  # lowered a bit more
                    spacing = int(HEIGHT * 0.08)  # space between lines
                    for i, text in enumerate(self.about_texts):
                        label = CoreLabel(text=text, font_size=int(HEIGHT*0.06), bold=True, color=(0,0,0,1))
                        label.refresh()
                        text_x = WIDTH//2 - label.texture.size[0]//2
                        text_y = start_y - i * spacing
                        Rectangle(texture=label.texture, pos=(text_x, text_y), size=label.texture.size)
                    
                    # --- Back button ---
                    button_width = int(WIDTH * 0.2)
                    button_height = int(HEIGHT * 0.1)
                    back_y = int(HEIGHT * 0.12)  # moved higher
                    self.back_button_pos = (WIDTH//2 - button_width//2, back_y)
                    self.back_button_size = (button_width, button_height)
                    Color(0.2, 0.6, 0.8, 1)
                    Rectangle(pos=self.back_button_pos, size=self.back_button_size)

                    # --- Back button text (normal, centered) ---
                    Color(1,1,1,1)  # white text
                    back_label = CoreLabel(text="Back", font_size=int(HEIGHT*0.04), bold=False)
                    back_label.refresh()
                    text_x = self.back_button_pos[0] + button_width/2 - back_label.texture.size[0]/2
                    text_y = self.back_button_pos[1] + button_height/2 - back_label.texture.size[1]/2
                    Rectangle(texture=back_label.texture, pos=(text_x, text_y), size=back_label.texture.size)

                if self.game_state == "gameover":
                    # Fried chicken image size (same as Home menu layout)
                    fc_img = fried_chicken_large
                    fc_x = WIDTH//2 - fc_img.width//2
                    fc_y = HEIGHT//2 + int(HEIGHT * 0.02)  # move slightly above center, like home menu
                    Rectangle(texture=fc_img.texture, pos=(fc_x, fc_y), size=(fc_img.width, fc_img.height))

                    # Game Over Text above the image
                    go_label = CoreLabel(text="Game Over!", font_size=int(HEIGHT*0.08), color=(1,0,0,1))
                    go_label.refresh()
                    text_x = WIDTH//2 - go_label.texture.size[0]//2
                    text_y = HEIGHT - 170  # Same as home menu title height
                    Rectangle(texture=go_label.texture, pos=(text_x, text_y), size=go_label.texture.size)

                    # --- Buttons (same positions as home menu) ---
                    button_width = int(WIDTH * 0.2)
                    button_height = int(HEIGHT * 0.1)
                    button_spacing = int(HEIGHT * 0.02)

                    # Retry button (same vertical position as Start Game in home menu)
                    self.retry_button_pos = (WIDTH//2 - button_width//2, HEIGHT//2 - int(HEIGHT*0.10))
                    self.retry_button_size = (button_width, button_height)

                    # Difficulty button (below Retry)
                    self.diff_button_pos = (WIDTH//2 - button_width//2,
                                            self.retry_button_pos[1] - button_height - button_spacing)
                    self.diff_button_size = (button_width, button_height)

                    # Home button (below Difficulty)
                    self.home_button_pos = (WIDTH//2 - button_width//2,
                                            self.diff_button_pos[1] - button_height - button_spacing)
                    self.home_button_size = (button_width, button_height)

                    # Draw rectangles
                    Color(0.2, 0.6, 0.8, 1)
                    Rectangle(pos=self.retry_button_pos, size=self.retry_button_size)
                    Rectangle(pos=self.diff_button_pos, size=self.diff_button_size)
                    Rectangle(pos=self.home_button_pos, size=self.home_button_size)

                    # Button text
                    button_font_size = int(HEIGHT * 0.04)
                    Color(1,1,1,1)

                    # Retry text
                    retry_label = CoreLabel(text="Retry", font_size=button_font_size)
                    retry_label.refresh()
                    Rectangle(
                        texture=retry_label.texture,
                        pos=(self.retry_button_pos[0] + button_width//2 - retry_label.texture.size[0]//2,
                            self.retry_button_pos[1] + button_height//2 - retry_label.texture.size[1]//2),
                        size=retry_label.texture.size
                    )

                    # Difficulty text
                    diff_label = CoreLabel(text=self.current_difficulty, font_size=button_font_size)
                    diff_label.refresh()
                    Rectangle(
                        texture=diff_label.texture,
                        pos=(self.diff_button_pos[0] + button_width//2 - diff_label.texture.size[0]//2,
                            self.diff_button_pos[1] + button_height//2 - diff_label.texture.size[1]//2),
                        size=diff_label.texture.size
                    )

                    # Home text
                    home_label = CoreLabel(text="Home", font_size=button_font_size)
                    home_label.refresh()
                    Rectangle(
                        texture=home_label.texture,
                        pos=(self.home_button_pos[0] + button_width//2 - home_label.texture.size[0]//2,
                            self.home_button_pos[1] + button_height//2 - home_label.texture.size[1]//2),
                        size=home_label.texture.size
                    )

                    return
                
            elif self.game_state == "settings":
                # --- Background & Ground ---
                Rectangle(texture=ground_img.texture, pos=(0, 0), size=(WIDTH, ground_img.height))
                
                # --- Title ---
                title_label = CoreLabel(text="Settings", font_size=int(HEIGHT * 0.08), color=(1,0,0,1))
                title_label.refresh()
                title_y = HEIGHT - 170
                Rectangle(texture=title_label.texture,
                        pos=(WIDTH//2 - title_label.texture.size[0]//2, title_y),
                        size=title_label.texture.size)

                # --- Sliders ---
                slider_spacing = int(HEIGHT * 0.12)
                slider_y_top = title_y - int(HEIGHT * 0.15)

                self.music_slider_pos = (WIDTH//2 - self.slider_width//2, slider_y_top)
                self.sfx_slider_pos = (WIDTH//2 - self.slider_width//2, slider_y_top - slider_spacing)

                text_offset = self.slider_height + int(HEIGHT * 0.02)

                # --- Music slider ---
                Color(0.2, 0.8, 0.2, 1)
                Rectangle(pos=self.music_slider_pos, size=(self.slider_width, self.slider_height))
                handle_x = self.music_slider_pos[0] + self.music_volume * self.slider_width - self.slider_height/2
                handle_y = self.music_slider_pos[1] - self.slider_height/2
                Color(0.8, 0.8, 0.2, 1)
                Rectangle(pos=(handle_x, handle_y), size=(self.slider_height*2, self.slider_height*2))

                music_label = CoreLabel(
                    text=f"Music: {int(self.music_volume*100)}%",
                    font_size=int(HEIGHT*0.03),
                    color=(0, 0, 0, 1)
                )
                music_label.refresh()
                Rectangle(
                    texture=music_label.texture,
                    pos=(WIDTH//2 - music_label.texture.size[0]//2,
                        self.music_slider_pos[1] + text_offset),
                    size=music_label.texture.size
                )

                # --- SFX slider ---
                Color(0.2, 0.8, 0.2, 1)
                Rectangle(pos=self.sfx_slider_pos, size=(self.slider_width, self.slider_height))
                handle_x = self.sfx_slider_pos[0] + self.sfx_volume * self.slider_width - self.slider_height/2
                handle_y = self.sfx_slider_pos[1] - self.slider_height/2
                Color(0.8, 0.8, 0.2, 1)
                Rectangle(pos=(handle_x, handle_y), size=(self.slider_height*2, self.slider_height*2))

                sfx_label = CoreLabel(
                    text=f"SFX: {int(self.sfx_volume*100)}%",
                    font_size=int(HEIGHT*0.03),
                    color=(0, 0, 0, 1)
                )
                sfx_label.refresh()
                Rectangle(
                    texture=sfx_label.texture,
                    pos=(WIDTH//2 - sfx_label.texture.size[0]//2,
                        self.sfx_slider_pos[1] + text_offset),
                    size=sfx_label.texture.size
                )

                # --- Buttons below sliders (even lower now) ---
                button_width = int(WIDTH * 0.2)
                button_height = int(HEIGHT * 0.1)
                button_spacing = int(HEIGHT * 0.02)
                extra_offset = int(HEIGHT * 0.05)  # now 5% of screen height, a little lower

                # Difficulty button
                self.diff_button_pos = (WIDTH//2 - button_width//2,
                                        self.sfx_slider_pos[1] - button_height - button_spacing - extra_offset)
                self.diff_button_size = (button_width, button_height)
                Color(0.2, 0.6, 0.8, 1)
                Rectangle(pos=self.diff_button_pos, size=self.diff_button_size)
                diff_label = CoreLabel(text=self.current_difficulty, font_size=int(HEIGHT*0.04))
                diff_label.refresh()
                Color(1,1,1,1)
                Rectangle(texture=diff_label.texture,
                        pos=(self.diff_button_pos[0] + button_width//2 - diff_label.texture.size[0]//2,
                            self.diff_button_pos[1] + button_height//2 - diff_label.texture.size[1]//2),
                        size=diff_label.texture.size)

                # Back button
                self.back_button_pos = (WIDTH//2 - button_width//2,
                                        self.diff_button_pos[1] - button_height - button_spacing)
                self.back_button_size = (button_width, button_height)
                Color(0.2, 0.6, 0.8, 1)
                Rectangle(pos=self.back_button_pos, size=self.back_button_size)
                back_label = CoreLabel(text="Back", font_size=int(HEIGHT*0.04))
                back_label.refresh()
                Color(1,1,1,1)
                Rectangle(texture=back_label.texture,
                        pos=(self.back_button_pos[0] + button_width//2 - back_label.texture.size[0]//2,
                            self.back_button_pos[1] + button_height//2 - back_label.texture.size[1]//2),
                        size=back_label.texture.size)
                
            # --- Gameplay updates ---
            if self.game_state == "playing":
                # Spawn chickens
                # Adjust max chickens and spawn interval based on difficulty
                if self.current_difficulty == "Easy":
                    max_chickens = min(int((self.max_chickens_base / 3) + self.score // 15), 5)
                    spawn_interval = max(2.0 - self.score * 0.01, 0.7)
                elif self.current_difficulty == "Medium":
                    max_chickens = min(int((self.max_chickens_base / 2) + self.score // 10), 7)
                    spawn_interval = max(1.5 - self.score * 0.015, 0.5)
                else:  # Hard
                    max_chickens = min(int((self.max_chickens_base / 1.5) + self.score // 7), 10)
                    spawn_interval = max(1.0 - self.score * 0.02, 0.4)

                if self.spawn_timer >= spawn_interval and len(self.chickens) < max_chickens:
                    self.chickens.append(new_chicken(self.score))
                    self.spawn_timer = 0
                    
                # Update chickens
                for chicken in self.chickens:
                    if chicken["state"] == "jumping" and not chicken["jump_sound_played"]:
                        if jump_sound: jump_sound.play()
                        chicken["jump_sound_played"] = True

                    # Horizontal movement
                    chicken["x"] += chicken["vx"]

                    # Bounce from screen edges
                    if chicken["x"] <= 0 or chicken["x"] >= WIDTH - chicken_width:
                        chicken["vx"] *= -1
                        chicken["x"] = max(0, min(chicken["x"], WIDTH - chicken_width))

                    if chicken["state"] == "jumping":
                        chicken["jump_progress"] += chicken["jump_speed"]
                        chicken_y = chicken["base_y"] + math.sin(chicken["jump_progress"]) * chicken["max_jump"]
                        if chicken["jump_progress"] >= math.pi:
                            if not chicken["shot"]:
                                self.misses += 1
                                if self.misses >= self.max_misses and not self.miss_sound_played:
                                    if failed_sound: failed_sound.play()
                                    self.miss_sound_played = True
                            chicken["state"] = "done"

                    elif chicken["state"] == "hit":
                        chicken_y = chicken.get("current_y", chicken["base_y"]) - chicken["fall_speed"]
                        if chicken_y <= 0:
                            chicken["state"] = "done"

                    chicken["current_y"] = chicken_y

                # Remove finished chickens
                self.chickens = [c for c in self.chickens if c["state"] != "done"]

                if len(self.chickens) == 0:
                    self.chickens.append(new_chicken(self.score))

                if self.misses >= self.max_misses:
                    self.game_state = "gameover"

                # --- Pause Button ---
                button_width = int(WIDTH * 0.15)   
                button_height = int(HEIGHT * 0.08)  
                self.pause_button_pos = (WIDTH - button_width - 20, HEIGHT - button_height - 20)

                # Draw button rectangle
                Color(0.8, 0.3, 0.3, 1) 
                Rectangle(pos=self.pause_button_pos, size=(button_width, button_height))

                # Draw Pause text
                pause_label = CoreLabel(text="Pause", font_size=int(HEIGHT*0.03))
                pause_label.refresh()
                Color(1,1,1,1)  # white text
                Rectangle(
                    texture=pause_label.texture,
                    pos=(self.pause_button_pos[0]+button_width//2 - pause_label.texture.size[0]//2,
                        self.pause_button_pos[1]+button_height//2 - pause_label.texture.size[1]//2),
                    size=pause_label.texture.size
                )

                # --- Draw chickens behind ground ---
                for chicken in self.chickens:
                    img = fried_chicken_small if chicken["state"] == "hit" else chicken_img
                    Rectangle(texture=img.texture,
                            pos=(chicken["x"], chicken["current_y"]),
                            size=(img.width, img.height))

                # --- Draw ground on top ---
                Rectangle(texture=ground_img.texture, pos=(0, 0), size=(WIDTH, ground_img.height))

            # --- Draw scoreboard always on top ---
            if self.game_state == "playing":
                score_font_size = int(HEIGHT * 0.04)
                score_label = CoreLabel(
                    text=f"Score: {self.score}  Misses: {self.misses}",
                    font_size=score_font_size,
                    color=(1,0,0,1)
                )
                score_label.refresh()
                Rectangle(
                    texture=score_label.texture,
                    pos=(10, HEIGHT - 40),
                    size=score_label.texture.size
                )

            # --- Pause menu ---
            if self.game_state == "paused":
                # --- Draw gameplay behind pause menu ---
                for chicken in self.chickens:
                    img = fried_chicken_small if chicken["state"] == "hit" else chicken_img
                    Rectangle(texture=img.texture,
                            pos=(chicken["x"], chicken["current_y"]),
                            size=(img.width, img.height))

                # Draw ground
                Rectangle(texture=ground_img.texture, pos=(0, 0), size=(WIDTH, ground_img.height))

                # --- Overlay dimming layer ---
                Color(0, 0, 0, 0.6)
                Rectangle(pos=(0, 0), size=(WIDTH, HEIGHT))

                # --- Title ---
                title_label = CoreLabel(text="Paused", font_size=int(HEIGHT * 0.08), color=(1,0,0,1))
                title_label.refresh()
                title_y = HEIGHT - 170
                Rectangle(texture=title_label.texture,
                        pos=(WIDTH//2 - title_label.texture.size[0]//2, title_y),
                        size=title_label.texture.size)

                # --- Sliders ---
                slider_spacing = int(HEIGHT * 0.12)
                slider_y_top = title_y - int(HEIGHT * 0.15)

                # Music slider
                self.music_slider_pos = (WIDTH//2 - self.slider_width//2, slider_y_top)
                Color(0.2, 0.8, 0.2, 1)
                Rectangle(pos=self.music_slider_pos, size=(self.slider_width, self.slider_height))
                handle_x = self.music_slider_pos[0] + self.music_volume * self.slider_width - self.slider_height/2
                handle_y = self.music_slider_pos[1] - self.slider_height/2
                Color(0.8, 0.8, 0.2, 1)
                Rectangle(pos=(handle_x, handle_y), size=(self.slider_height*2, self.slider_height*2))

                Color(1,1,1,1)
                music_label = CoreLabel(text=f"Music: {int(self.music_volume*100)}%", font_size=int(HEIGHT*0.03))
                music_label.refresh()
                Rectangle(
                    texture=music_label.texture,
                    pos=(WIDTH//2 - music_label.texture.size[0]//2,
                        self.music_slider_pos[1] + self.slider_height + int(HEIGHT*0.02)),
                    size=music_label.texture.size
                )

                # SFX slider (below Music)
                self.sfx_slider_pos = (WIDTH//2 - self.slider_width//2, slider_y_top - slider_spacing)
                Color(0.2, 0.8, 0.2, 1)
                Rectangle(pos=self.sfx_slider_pos, size=(self.slider_width, self.slider_height))
                handle_x = self.sfx_slider_pos[0] + self.sfx_volume * self.slider_width - self.slider_height/2
                handle_y = self.sfx_slider_pos[1] - self.slider_height/2
                Color(0.8, 0.8, 0.2, 1)
                Rectangle(pos=(handle_x, handle_y), size=(self.slider_height*2, self.slider_height*2))

                Color(1,1,1,1)
                sfx_label = CoreLabel(text=f"SFX: {int(self.sfx_volume*100)}%", font_size=int(HEIGHT*0.03))
                sfx_label.refresh()
                Rectangle(
                    texture=sfx_label.texture,
                    pos=(WIDTH//2 - sfx_label.texture.size[0]//2,
                        self.sfx_slider_pos[1] + self.slider_height + int(HEIGHT*0.02)),
                    size=sfx_label.texture.size
                )

                # --- Buttons below sliders with extra offset ---
                button_width = int(WIDTH * 0.25)
                button_height = int(HEIGHT * 0.1)
                button_spacing = int(HEIGHT * 0.03)
                extra_offset = int(HEIGHT * 0.05)  # extra space to push buttons lower

                # Resume button
                self.resume_button_pos = (
                    WIDTH//2 - button_width//2,
                    self.sfx_slider_pos[1] - button_height - button_spacing - extra_offset
                )
                self.resume_button_size = (button_width, button_height)
                Color(0.2, 0.6, 0.8, 1)
                Rectangle(pos=self.resume_button_pos, size=self.resume_button_size)
                resume_label = CoreLabel(text="Resume", font_size=int(HEIGHT*0.05))
                resume_label.refresh()
                Color(1,1,1,1)
                Rectangle(
                    texture=resume_label.texture,
                    pos=(self.resume_button_pos[0]+button_width//2 - resume_label.texture.size[0]//2,
                        self.resume_button_pos[1]+button_height//2 - resume_label.texture.size[1]//2),
                    size=resume_label.texture.size
                )

                # Exit button
                self.exit_button_pos = (
                    WIDTH//2 - button_width//2,
                    self.resume_button_pos[1] - button_height - button_spacing
                )
                self.exit_button_size = (button_width, button_height)
                Color(0.8, 0.2, 0.2, 1)
                Rectangle(pos=self.exit_button_pos, size=self.exit_button_size)
                exit_label = CoreLabel(text="Exit", font_size=int(HEIGHT*0.05))
                exit_label.refresh()
                Color(1,1,1,1)
                Rectangle(
                    texture=exit_label.texture,
                    pos=(self.exit_button_pos[0]+button_width//2 - exit_label.texture.size[0]//2,
                        self.exit_button_pos[1]+button_height//2 - exit_label.texture.size[1]//2),
                    size=exit_label.texture.size
                )

                return
            
    def update_slider(self, x):
        """Update SFX or Music volume based on slider position."""
        if self.active_slider == "sfx":
            self.sfx_volume = max(0.0, min((x - self.sfx_slider_pos[0]) / self.slider_width, 1.0))
            set_sfx_volume(self.sfx_volume)
        elif self.active_slider == "music":
            self.music_volume = max(0.0, min((x - self.music_slider_pos[0]) / self.slider_width, 1.0))
            self.music_manager.set_volume(self.music_volume)
                
class ChickenShooterApp(App):
    def build(self):
        return GameWidget()

if __name__ == "__main__":
    set_sfx_volume(sfx_volume)  # keep SFX function as-is
    ChickenShooterApp().run()
