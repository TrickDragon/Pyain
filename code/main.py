import os
from settings import *
from pytmx.util_pygame import load_pygame
from os.path import join

# Absolute path setup
BASE_DIR = os.path.dirname(__file__)
MAP_PATH = os.path.join(BASE_DIR, '..', 'data', 'maps', 'world.tmx')
HOSPITAL_PATH = os.path.join(BASE_DIR, '..', 'data', 'maps', 'hospital.tmx')

from sprites import Sprite, AnimatedSprite, MonsterPatchSprite, BorderSprite, CollidableSprite
from entities import Player, Character
from groups import AllSprites
from support import *
import json
from dialog import DialogTree
import pickle
import random

class Game:
    def __init__(self):
        pygame.init()
        self.display_surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption('Pyiam')
        self.clock = pygame.time.Clock()

        # groups
        self.all_sprites = AllSprites()
        self.collision_sprites = pygame.sprite.Group()
        self.character_sprites = pygame.sprite.Group()
        self.transition_sprites = pygame.sprite.Group()
        self.monster_sprites = pygame.sprite.Group()

        # transition / tint
        self.transition_target = None
        self.tint_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.tint_mode = 'untint'
        self.tint_progress = 0
        self.tint_direction = -1
        self.tint_speed = 600

        self.import_assets()
        self.setup(self.tmx_maps['world'], 'house')

        self.dialog_tree = None

        self.encounter_cooldown = 0.5  # seconds between checks
        self.encounter_time = 0  # accumulates while standing in grass
        self.encounter_threshold = 2.5  # minimum time before encounters begin


    #def load_saved_position(self):
    #    try:
    #        with open('gamesave.json') as load_file:
    #            data = json.load(load_file)
    #            return (data['pos_x'], data['pos_y'])
    #    except (FileNotFoundError, KeyError):
    #        return None

    def get_player_position(self):
        if self.player:
            return {'pos_x': self.player.rect.centerx, 'pos_y': self.player.rect.centery}
        return {'pos_x': 0, 'pos_y': 0}

    def trigger_encounter(self, patch):
        print("goteem")
        chosen = random.choice(patch.monsters)
        print(f"A wild {chosen} (Level {patch.level}) appeared in the {patch.biome} biome!")
        self.tint_mode = 'tint'
        self.display_surface.fill('black')
        # You could pause game logic here or fade into a battle scene

    def import_assets(self):
        self.tmx_maps = {
            'world': load_pygame(MAP_PATH),
            'hospital': load_pygame(HOSPITAL_PATH)
        }

        self.overworld_frames = {
            'water': import_folder(BASE_DIR, '..', 'graphics', 'tilesets', 'water'),
            'coast': coast_importer(24, 12, BASE_DIR, '..', 'graphics', 'tilesets', 'coast'),
            'characters': all_character_import(BASE_DIR, '..', 'graphics', 'characters')
        }

        #print(self.overworld_frames['coast'])

    def setup(self, tmx_map, player_start_pos):
        # terrain
        for layer in ['Terrain', 'Terrain Top']:
            for x,y, surf in tmx_map.get_layer_by_name(layer).tiles():
                Sprite((x * TILE_SIZE, y * TILE_SIZE), surf, self.all_sprites)

        # water
        for obj in tmx_map.get_layer_by_name('Water'):
            for x in range(int(obj.x), int(obj.x + obj.width), TILE_SIZE):
                for y in range(int(obj.y), int(obj.y + obj.height), TILE_SIZE):
                    AnimatedSprite((x, y), self.overworld_frames['water'], self.all_sprites,
                                   WORLD_LAYERS['water'])

        # coast
        for obj in tmx_map.get_layer_by_name('Coast'):
            terrain = obj.properties['terrain']
            side = obj.properties['side']
            AnimatedSprite((obj.x, obj.y), self.overworld_frames['coast'][terrain][side], self.all_sprites,
                           WORLD_LAYERS['bg'])

        # objects
        for obj in tmx_map.get_layer_by_name('Objects'):
            if obj.name == 'top':
                Sprite((obj.x, obj.y), obj.image, self.all_sprites)
            else:
                CollidableSprite((obj.x, obj.y), obj.image, (self.all_sprites, self.collision_sprites))

        # grass patches
        for obj in tmx_map.get_layer_by_name('Monsters'):
            MonsterPatchSprite((obj.x, obj.y), obj.image, (self.all_sprites, self.monster_sprites),
                               obj.properties['biome'], obj.properties['monsters'], obj.properties['level'])
        # collision objects
        for obj in tmx_map.get_layer_by_name('Collisions'):
            BorderSprite((obj.x, obj.y), pygame.Surface((obj.width, obj.height)), (self.all_sprites, self.collision_sprites))

        #saved_pos = self.load_saved_position()

        for obj in tmx_map.get_layer_by_name('Entities'):
            if obj.name == 'Player':
                if obj.properties['pos'] == player_start_pos:
                    self.player = Player(
                        pos=[3000,3000],
                        frames=self.overworld_frames['characters']['player'],
                        groups=self.all_sprites,
                        facing_direction=obj.properties['direction'],
                        collision_sprites=self.collision_sprites)

            else:
                Character(
                    pos=(obj.x, obj.y),
                    frames=self.overworld_frames['characters'][obj.properties['graphic']],
                    groups=(self.all_sprites, self.collision_sprites),
                    facing_direction=obj.properties['direction'])

        # dialog system
    def input(self):
        if not self.dialog_tree:
            keys = pygame.key.get_just_pressed()
            if keys[pygame.K_SPACE]:
                for character in self.character_sprites:
                    if check_connections(100, self.player, character):
                        self.player.block()
                        character.change_facing_direction(self.player.rect.center)
                        self.create_dialog(character)
                        character.can_rotate = False

    def create_dialog(self, character):
        if not self.dialog_tree:
            self.dialog_tree = DialogTree(character, self.player, self.all_sprites, self.fonts['dialog'],
                                          self.end_dialog)

    def end_dialog(self, character):
        self.dialog_tree = None
        self.player.unblock()

    # transition system
    def transition_check(self):
        sprites = [sprite for sprite in self.transition_sprites if sprite.rect.colliderect(self.player.hitbox)]
        if sprites:
            self.player.block()
            self.transition_target = sprites[0].target
            self.tint_mode = 'tint'

    def tint_screen(self, dt):
        if self.tint_mode == 'untint':
            self.tint_progress -= self.tint_speed * dt

        if self.tint_mode == 'tint':
            self.tint_progress += self.tint_speed * dt
            if self.tint_progress >= 255:
                self.setup(self.tmx_maps[self.transition_target[0]], self.transition_target[1])
                self.tint_mode = 'untint'
                self.transition_target = None

        self.tint_progress = max(0, min(self.tint_progress, 255))
        self.tint_surf.set_alpha(self.tint_progress)
        self.display_surface.blit(self.tint_surf, (0, 0))


    def run(self):
        while True:
            dt = self.clock.tick(30) / 1000
            # event loop
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    with open('gamesave.json', 'w') as store_file:
                        json.dump(self.get_player_position(), store_file)
                    pygame.quit()
                    exit()


            # game logic
            self.all_sprites.update(dt)
            # Check for monster patch collisions
            current_patch = None
            for patch in self.monster_sprites:
                if patch.rect.colliderect(self.player.hitbox):
                    current_patch = patch
                    break

            if current_patch:
                self.encounter_time += dt
                if self.encounter_time >= self.encounter_threshold:
                    # Slow-roll chance every cooldown interval
                    self.encounter_cooldown -= dt
                    if self.encounter_cooldown <= 0:
                        self.encounter_cooldown = 0.5
                        # Increase chance over time
                        chance = min(0.1 + (self.encounter_time - self.encounter_threshold) * 0.1, 0.5)
                        if random.random() < chance:
                            self.trigger_encounter(current_patch)
                            self.encounter_time = 0
            else:
                self.encounter_time = 0
                self.encounter_cooldown = 0.5


            self.display_surface.fill('black')
            self.all_sprites.draw(self.player.rect.center)
            pygame.display.update()



if __name__ == '__main__':
    game = Game()
    game.run()
    print()

# 1. Bug Fix, Collision = Overlay Fixes
# 2. Screen Pops out
# 3. Battle Logic