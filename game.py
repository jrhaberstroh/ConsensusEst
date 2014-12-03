#!/usr/bin/env python

import pygame, math, sys
import numpy as np, scipy as sp
import random
import logging

import consensusest.kalman_filter as kalman_filter
import consensusest.sensor as sense

from pygame.locals import *

base = 'consensusest/images'
img_car = base + '/car.png'
img_est = base + '/crosshair.png'
img_sensor = base + '/satellite-dish-icon-hi.png'
 
flags = DOUBLEBUF 

DIRECTION_UP = 0
DIRECTION_DOWN = 1
DIRECTION_LEFT = 2
DIRECTION_RIGHT = 3
DRONE_RANGE=1000

BLACK = (0,0,0)
MAX_Y = 768
MAX_X = 1024


class event:
    def __init__(self):
        self.name = "generic"

class event_manager:
    def __init__(self):
        from weakref import WeakKeyDictionary
        self.listeners = WeakKeyDictionary()

    def register_listener(self, listener):
        self.listeners [ listener ] = 1

    def post(self, event):
        for listener in self.listeners.keys():
            listener.notify(event)

class tick_event(event):
    def __init__(self):
        self.name = "tick"

class quit_event(event):
    def __init__(self):
        self.name = "quit"

class car_move_request(event):
    def __init__(self, direction):
        self.name = "request"
        self.direction = direction

class car_move_event(event):
    def __init__(self, car):
        self.name = "move"
        self.car = car

class measurement_event(event):
    def __init__(self, measurement):
        self.name = "meas"
        self.measurement = measurement

class sensor_draw_event(event):
    def __init__(self, sensor):
        self.name = "sens"
        self.sensor = sensor

class keyboard_controller:
    def __init__(self, event_manager):
        self.event_manager = event_manager
        self.event_manager.register_listener(self)
    
    def notify(self, event):
        
        # if not isinstance(event,tick_event):
         #   print ("keyboard notified ")
         #   print event

        
            
        for event in pygame.event.get():
            ev = None
            
            if not hasattr(event, 'key'):
                continue
            
            if event.type == QUIT:
                ev = quit_event()
                
            elif event.type == KEYDOWN:
                if event.key == K_RIGHT:
                    direction = DIRECTION_RIGHT
                    ev = car_move_request(direction)
                elif event.key == K_LEFT:
                    direction = DIRECTION_LEFT
                    ev = car_move_request(direction)
                elif event.key == K_UP:
                    direction = DIRECTION_UP
                    ev = car_move_request(direction)
                elif event.key == K_DOWN:
                    direction = DIRECTION_DOWN
                    ev = car_move_request(direction)
                elif event.key == K_ESCAPE:
                    ev = quit_event()
                    
            self.event_manager.post(ev)


class sensor:        
    def __init__(self, event_manager, mode):
        self.event_manager = event_manager
        self.event_manager.register_listener(self)
        self.converged = 0
        if mode=='NETWORK':
            self.network_init()
        if mode=='DRONE':
            self.drone_init()

    def drone_init(self):
        init_pos = np.matrix([20., 20.]).T
        init_err = np.eye(2) * 10.
        self.dyn_model       = np.eye(2)
        self.dyn_noise_model = np.eye(2)
        self.dyn_noise_cov   = np.eye(2) * .1
        # Empty-initialize network and positions
        self.N = 0
        self.net     = sense.LiveSensorNetwork(init_pos, init_err)
        self.net_pos = []
        
        self.dish_img = pygame.image.load(img_sensor).convert()
        self.crosshair_img = pygame.image.load(img_est).convert()
        self.drone=True
        self.feedback=False
        self.active=False

        n_drones = 2
        for i in xrange(n_drones):
            rand_pos = np.array([[random.uniform(0, MAX_X), random.uniform(0, MAX_Y)]]).T
            drone = sense.Sensor(model = 
                                 [[random.uniform(0, 1), random.uniform(0, 1)],
                                  [random.uniform(0, 1), random.uniform(0, 1)]],
                                 meas_cov = [[5., 0.],
                                             [0., 5.]])
            self.net.add_sensor(drone, range(self.N), x0 = rand_pos)
            self.net_pos.append(rand_pos)
            self.net.stream_data(rand_pos, [i])
            self.N += 1

        ## Append two sensors to the network
        #xm = sense.Sensor([[1., 0.]], [[5.]]) # Measures x
        #self.net.add_sensor(xm)
        #xm_pos = np.array([20, MAX_Y/2])
        #self.net_pos.append(xm_pos)
        #self.N += 1
        #
        #ym = sense.Sensor([[0., 1.]], [[5.]]) # Measures y
        #self.net.add_sensor(ym, [0])
        #ym_pos = np.array([MAX_X/2, 20])
        #self.net_pos.append(ym_pos)
        #self.N += 1
        

    def network_init(self):
        init_pos = np.matrix([20., 20.]).T
        init_err = np.eye(2) * 10.
        self.dyn_model       = np.eye(2)
        self.dyn_noise_model = np.eye(2)
        self.dyn_noise_cov   = np.eye(2) * .3
        # Empty-initialize network and positions
        self.N = 0
        self.net     = sense.LiveSensorNetwork(init_pos, init_err)
        self.net_pos = []

        self.dish_img = pygame.image.load(img_sensor).convert()
        self.crosshair_img = pygame.image.load(img_est).convert()
        self.drone=False
        self.active=True
        
        # Append two sensors to the network
        xm = sense.Sensor([[1., 0.]], [[5.]]) # Measures x
        self.net.add_sensor(xm)
        xm_pos = np.array([20, MAX_Y/2])
        self.net_pos.append(xm_pos)
        self.N += 1
        
        ym = sense.Sensor([[0., 1.]], [[5.]]) # Measures y
        self.net.add_sensor(ym, [0])
        ym_pos = np.array([MAX_X/2, 20])
        self.net_pos.append(ym_pos)
        self.N += 1
        

    def draw(self):
        self.event_manager.post(sensor_draw_event(self))

    def notify(self,event):
        if (isinstance(event,tick_event)):
            if self.converged == 0:
                self.draw()
            if self.active:
                self.draw()
        if (isinstance(event,measurement_event)):
            if self.converged > 200:
                self.active = True
            meas = np.array(event.measurement)
            if not self.drone:
                self.net.stream_data(meas)
                self.net.iterate_filter(dyn_model = self.dyn_model,
                                        dyn_noise_model = self.dyn_noise_model,
                                        dyn_noise_cov = self.dyn_noise_cov)
            if self.drone:
                for i in xrange(self.N):
                    sensor_pos = self.net_pos[i].flatten()
                    target_pos = meas.flatten()
                    target_dist = sensor_pos - target_pos
                    target_mag = np.sqrt(np.sum(np.square(target_dist)))
                    logging.debug("DIST {}: {}".format(i, target_dist))
                    logging.debug("MAG {}: {}".format(i, target_mag))
                    if (target_mag < DRONE_RANGE):
                        self.converged += 1
                        self.net.stream_data(meas, [i])
                        logging.debug(self.net_pos[i].shape)
                        belief = self.net[i]
                        logging.debug(belief.shape)
                        logging.debug(sensor_pos.shape)
                        if self.feedback:
                            self.net_pos[i][0] += (belief[0,0] - sensor_pos[0]) / 5
                            self.net_pos[i][1] += (belief[1,0] - sensor_pos[1]) / 5
                self.net.iterate_filter(dyn_model = self.dyn_model,
                        dyn_noise_model = self.dyn_noise_model,
                        dyn_noise_cov = self.dyn_noise_cov)



class car:
    def __init__(self,x,y,speed,direction,turn_speed,max_forward_speed,max_reverse_speed,delta,event_manager):
        self.speed = speed
        self.direction = direction
        self.turn_speed = turn_speed
        self.max_forward_speed = max_forward_speed
        self.max_reverse_speed = max_reverse_speed
        self.x = x
        self.y = y
        self.delta = delta
        self.event_manager = event_manager
        self.counter = 0

        self.car_img = pygame.image.load(img_car).convert()

    def update_key(self,click_dir):
        if (click_dir == DIRECTION_UP):
            self.speed += self.delta
        elif (click_dir == DIRECTION_DOWN):
            self.speed -= self.delta
        elif (click_dir == DIRECTION_RIGHT):
            self.turn_speed -= self.delta
        elif (click_dir == DIRECTION_LEFT):
            self.turn_speed += self.delta

        if (self.speed > self.max_forward_speed):
            self.speed = self.max_forward_speed
        elif (self.speed < self.max_reverse_speed):
            self.speed = self.max_reverse_speed

        self.direction = self.direction + 0.6 * self.turn_speed
        rad = self.direction * math.pi / 180
        self.x += self.speed * math.sin(rad)
        self.y += self.speed * math.cos(rad)
       
        if self.y < 0:
            self.y = 0 
        elif self.y > MAX_Y:
            self.y = MAX_Y
        if self.x < 0:
            self.x = 0
        elif self.x > MAX_X:
            self.x = MAX_X        
        
    
    def update(self):

        self.direction = self.direction + 0.6 * self.turn_speed
        rad = self.direction * math.pi / 180
        self.x += self.speed * math.sin(rad)
        self.y += self.speed * math.cos(rad)
       

        if (self.speed > self.max_forward_speed):
            self.speed = self.max_forward_speed
        elif (self.speed < self.max_reverse_speed):
            self.speed = self.max_reverse_speed


        if self.y < 0:
            self.y = 0 
        elif self.y > MAX_Y:
            self.y = MAX_Y
        if self.x < 0:
            self.x = 0
        elif self.x > MAX_X:
            self.x = MAX_X        
        


    def draw(self):
        ev = car_move_event( self )
        self.event_manager.post( ev )

        self.counter += 1

        if self.counter % 3 == 0 :
            ev2 = measurement_event((self.x, self.y))
            self.event_manager.post( ev2 )        

    def notify(self, event):
        if isinstance( event, car_move_request):
            self.update_key(event.direction)
            self.draw()

        if isinstance( event, tick_event):
            self.update()
            self.draw()

class pygame_view:
    def __init__(self, event_manager):
        self.event_manager = event_manager
        self.event_manager.register_listener(self)

        pygame.init()
        self.window = pygame.display.set_mode( (MAX_X,MAX_Y), flags )
        self.window.set_alpha(None)


        pygame.display.set_caption( 'Run Away!' )
        self.background = pygame.Surface( self.window.get_size() ).convert()
        self.background.fill( (0,0,0) )


        self.window.blit( self.background, (0,0) )
        pygame.display.flip()

        self.dish_center = (0,0)
        self.car_center = (0,0)
        self.crosshair_center = (0,0)

    def show_bg(self):
        self.window.blit( self.background, (0,0) )
        pygame.display.flip()


    def show_car(self, car):
        


        rotated = pygame.transform.rotate(car.car_img, car.direction)
        rect = rotated.get_rect()
        position = (car.x, car.y)

        rect.center = position
        
        # print position 

        self.window.blit(rotated,rect)
        pygame.display.flip()


    def show_sensor(self, sensor):

        dish = sensor.dish_img
        crosshair = sensor.crosshair_img
  
        dish_rect = dish.get_rect()
        for i in xrange(sensor.N):
            pos = sensor.net_pos[i]
            pos_est = sensor.net[i]
            dish_rect.center = (pos[0], pos[1])
            crosshair_rect = crosshair.get_rect()
            crosshair_rect.center = pos_est
            self.dish_center = dish_rect.center
            self.crosshair_center = crosshair_rect.center
            self.window.blit(sensor.dish_img,dish_rect)
            self.window.blit(sensor.crosshair_img,crosshair_rect)

        pygame.display.flip()
    
    def notify(self, event):
        if (isinstance(event, car_move_event)):
            self.show_car(event.car)
        if (isinstance(event, sensor_draw_event)):
            self.show_sensor(event.sensor)
        if (isinstance(event, tick_event)):
            self.show_bg()

class run_loop:
    def __init__(self, event_manager):
        self.event_manager = event_manager
        self.event_manager.register_listener(self)
        self.running = True

    def run(self):
        while self.running:
            event = tick_event()
            self.event_manager.post( event)

    def notify(self, event):
        if isinstance( event, quit_event ):
            self.running = False
 
class game:
    def __init__(self, event_manager):
        self.event_manager = event_manager
        self.event_manager.register_listener(self)

        self.car = car(x=100,y=100,speed=0,direction=0,turn_speed=0,max_forward_speed = 15,max_reverse_speed = 5,delta = 2,event_manager = self.event_manager)


        self.sensor = sensor(event_manager=self.event_manager, mode='DRONE')

    def notify(self, event):
        self.car.notify(event)
        self.sensor.notify(event)
           

def main():
    ev_manager = event_manager()

    keybd = keyboard_controller(ev_manager)
    spinner = run_loop (ev_manager)
    py_view = pygame_view(ev_manager)
    gm = game( ev_manager )

    spinner.run()
 
 

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
