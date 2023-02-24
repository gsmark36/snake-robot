"""snake_basic controller."""

#********* IMPORTS *********#
# Import basic py libs
import cv2 as cv2   # opencv
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray
from geometry_msgs.msg import Twist
# You may need to import some classes of the controller module. Ex:
#  from controller import Robot, Motor, DistanceSensor
#from controller import Robot
# from controller import Motor


# Motor position (rads) to keep legs
KEEP_LEGS_RAD = -2.0

#********* GLOBAL CONSTANTS *********#

# Number of motors: 6 actuated body segments and 4 legs
NUM_MOTORS = 10  
# Get Names of motors as per webots
MOTOR_NAMES = ["motor_1", "motor_2",     "motor_3",     "motor_4",     "motor_5",
                "motor_6", "motor_leg_1", "motor_leg_2", "motor_leg_3", "motor_leg_4"]
#********* HELPER FUNCTIONS *********#
"""
Put helper functions here. E.g., Gait equation, path selection, and obstacle avoidance
"""
class SnakeRobotController:
    def init(self, webots_node, properties):
        self.robot = webots_node.robot
        # get the time step of the current world.
        self.timestep = int(self.robot.getBasicTimeStep())       # in milliseconds
        rclpy.init(args=None)
        self.node = rclpy.create_node('snake_basic')
        self.pub = self.node.create_publisher( Float32MultiArray, 'motor', 10)
        self.node.get_logger().info(f"simulation timestep = {self.timestep} ms")

        #********* INITIALISATION *********#

        # !!!!!!!! TURN SNAKE MODE ON OR OFF !!!!!!!! #
        # True to keep legs, False to extend legs
        self.snake_mode = False   
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! #

        # Initial locomotion values
        self.spine_offset = 0.0  # this controls turning. negative vals to turn left, positive turns right
        self.amplitude = 1.0     # Gait eqn amplitude
        self.phase = 0.0         # current locomotion phase
        self.walk_ampl = 0.6     # Walk amplitude in rads (for body swaying)
        self.freq = 1.4          # Gait freq in Hz   

        # Initialise list to store target motor positions
        self.target_position = np.zeros(NUM_MOTORS)

        #********* START CAMERA *********#
        """
        Command to start camera and get image data from it
        """
        ## image capture rate of camera
        CAMERA_RATE = self.timestep      # this is default timestep (32 ms), so camera will refresh at 31.25Hz
        # CAMERA_RATE = 2500          # this is the slower setting as per pape;, one image per 2.5s (0.4 Hz)
        self.node.get_logger().info(f"camera takes one pic every {CAMERA_RATE} ms")
        # Start camera
        self.camera = self.robot.getDevice('camera')
        self.camera.enable(CAMERA_RATE)
        self.img_width = self.camera.getWidth()
        self.img_height = self.camera.getHeight()
        self.node.get_logger().info(f"dims of img: w={self.img_width}, h={self.img_height}")
        #********* START MOTORS *********#
        """
        Commands to start motors and initialise their initial positions and velocity
        """

        # Store motors as a list
        self.motors = [self.robot.getDevice(MOTOR_NAMES[i]) for i in range(NUM_MOTORS)]

        # Set min/max position of motors
        self.min_motor_positions = [self.motors[i].getMinPosition() for i in range(NUM_MOTORS)]
        self.max_motor_positions = [self.motors[i].getMaxPosition() for i in range(NUM_MOTORS)]
        self.node.get_logger().info(f"min motor pos = {self.min_motor_positions}") # Debug
        self.node.get_logger().info(f"max motor pos = {self.max_motor_positions}") # Debug
        # Set initial positions of motor
        for i in range(NUM_MOTORS):
            self.motors[i].setPosition(0)
            # motors[i].setVelocity(float('inf'))

    def restrict(self, target_pos, min_pos, max_pos):
        """
        Clamps motor position to within min/max values 
        """
        if (min_pos == 0 and max_pos == 0):     # weird case, just remain unchanged
            return target_pos
        else:   # clamps value to limit
            return max(min_pos, min(max_pos, target_pos))


    def get_image(self):
        """
        Gets image and convert into cv2 readable format

        Reference: https://github.com/lukicdarkoo/webots-example-visual-tracking
        """
        # Get image after 1 step
        #self.robot.step(self.timestep)          # UNCOMMENT IF IMG TYPE IS NONE
        #cameraData = self.camera.getImage()
        cameraData = self.camera.getImageArray()

        # Process image into numpy array
        # img = np.frombuffer(cameraData, np.uint8).reshape((img_height, img_width, 4))
        # print(img)
        img = np.asarray(cameraData, dtype=np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)

        
        # print(f"cv ver = {cv2.__version__ }")     # Debug
        img_cv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        img_cv = cv2.rotate(img_cv, cv2.ROTATE_90_CLOCKWISE)
        img_cv = cv2.flip(img_cv, 1)

        return img_cv
    
    def segmentation(self, img):
        """
        Segement the image into ground pixels and non-ground pixels.
        Multiple methods will be implemented:
        1. Naive thresholding (done)
        2. SVM (TODO)
        3. Others (TODO)
        """
        h, w, _ = img.shape
        mid_w = int(np.floor(w / 2))
        w_low = mid_w - int(np.floor(w / 10))
        w_high = mid_w + int(np.floor(w / 10))
        h_low = h - int(np.floor(h / 10))
        ground_ref_img = img[h_low:h, w_low:w_high, :]    # 24x8 image, can be tuned later
        # Debugging!
        # print(ground_ref_img.shape)
        # img_RGB = cv2.cvtColor(ground_ref_img, cv2.COLOR_HSV2RGB)
        # cv2.namedWindow("Ground reference image")
        # cv2.imshow("Ground reference image", img_RGB)
        # cv2.waitKey(0)
        # print(ground_ref_img)
        tol = 10
        low_H, low_S, low_V = np.min(ground_ref_img, axis=(0,1)) - tol
        high_H, high_S, high_V = np.max(ground_ref_img, axis=(0,1)) + tol
        # print(low_H, low_S, low_V, high_H, high_S, high_V)
        mask = cv2.inRange(img, np.array([low_H, low_S, low_V]), np.array([high_H, high_S, high_V]))
        # cv2.namedWindow("Mask")
        # cv2.imshow("Mask", mask)
        # cv2.waitKey(0)
        return mask


    def trajectory_sampling(self, h, w):
        """
        Sample 5 trajectories (for now only 1) that will be tested,
        return the end points (can be modified to return a whole trajectory).
        """
        # Without a motion model, I cannot determine where the snake head will land
        # For now, I will only return one specific point for moving straight forward
        mid_w = int(np.floor(w / 2))
        h_forward = h - int(np.floor(h / 4))

        candidate_points = []
        candidate_points.append(np.array([h_forward, mid_w]))
        return candidate_points


    def collision_check(self, mask, point):
        """
        Check whether the end point of a trajectory will collide with an obstacle,
        using the ground segmentation mask.
        """
        return mask[point[0], point[1]]


    def get_direction(self, img):
        h, w, _ = img.shape

        # Get the ground segmentation mask
        mask = self.segmentation(img)

        # Sample some trajectories, return the end points
        candidate_points = self.trajectory_sampling(h, w)

        # Collision checking for the candidate points
        # It can be extended to check the whole trajectory, instead of just the end points
        # Will be changed for multiple points
        for point in candidate_points:
            if self.collision_check(mask, point):
                return 0.0
            else:
                # For now, either move straight forward, or turn right if obstacle detected
                return 0.3

        # Should never reach here
        return 0.0

    def step(self):

        ## ***** 1. Read the sensors ***** ##

        # Get an image from the camera and convert to OpenCV format
        img_cv = self.get_image()

        ## ***** 2. Calculate output actuator commands here ***** ##

        # (outdated)Make robot go straight. But if you want it to turn, then adjust accordingly
        # Get the direction using trajectory sampling and collision checking in perception space
        spine_offset = self.get_direction(img_cv)
        print(spine_offset)

        # Increase phase according to elapsed time
        self.phase -= (self.timestep / 1000) * self.freq * 2 * np.pi

        # Constants that enable S-shaped body of robot (per demo)
        A = [-0.7, 1, 1, 0, -1, -1]

        # Calculate motor positions for body swaying
        for i in range(6):  # up to 6 because motors 0-5 for body. 6-9 for leg
            self.target_position[i] = self.walk_ampl * self.amplitude * A[i] * np.sin(self.phase) + spine_offset
            # The above is a sample eqn for body wave. Replace it with gait eqn as needed!!!


        # Calculate leg movements
        if self.snake_mode:      # in snake mode, so legs are kept
            for i in range(6, NUM_MOTORS):
                self.target_position[i] = KEEP_LEGS_RAD

        else:   # Not in snake mode, so rotate legs as robot walk
            self.target_position[6] = self.phase
            self.target_position[7] = self.phase + np.pi
            self.target_position[8] = self.phase + np.pi
            self.target_position[9] = self.phase

        ## ***** 3. Set motor actuation ***** ##
        for i in range(NUM_MOTORS):

            # Ensure does not exceed min/max of motor
            self.target_position[i] = self.restrict(self.target_position[i], self.min_motor_positions[i], self.max_motor_positions[i])

            # Debug
            self.node.get_logger().info(f"final target pos = {self.target_position}")

            # Finally, set motor position
            # motors[i].setVelocity(target_position[i])
            self.motors[i].setPosition(self.target_position[i])
        
        msg = Float32MultiArray()
        msg.data = set(self.target_position.flatten())
        self.pub.publish(msg)
        #rclpy.spin_once(self.node)

'''
def main(args):
    rclpy.init()
    controller = SnakeRobotController(webots_node=args["robot_description"], properties=None)

    #while controller.robot.step(controller.timestep) != -1:
    while rclpy.ok():
        #rclpy.spin_once(controller)
        controller.step()


    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    controller.destroy_node()
    rclpy.shutdown()
'''