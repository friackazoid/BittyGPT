"""
This script is used to test the execution of a command from a JSON file.
"""


import json
import sys
import time

from pydantic import BaseModel

import SerialCommunication as sc
import RobotController as rc


class Leg(BaseModel):
    sholder: int
    elbow: int


class Pose(BaseModel):
    left_front: Leg
    left_back: Leg
    right_front: Leg
    right_back: Leg


class Command(BaseModel):
    poses: list[Pose]
    description: str


def read_command(file_path: str) -> Command:
    with open(file_path, 'r') as file:
        data = json.load(file)
        command = Command(**data)
    return command


def make_command(command: Command) -> list:
    c_poses = []
    for pose in command.poses:
        c_pose = [0] * 8 + [
            pose.left_front.sholder,
            pose.right_front.sholder,
            pose.right_back.sholder,
            pose.left_back.sholder,
            pose.left_front.elbow,
            pose.right_front.elbow,
            pose.right_back.elbow,
            pose.left_back.elbow
        ]
        c_poses.append(c_pose)

    return c_poses


def execute_command(c_poses: list):
    all_ports = sc.Communication.list_available_ports()

    if all_ports:
        port_name = "/dev/ttyUSB0"  # Select the first available port
        with sc.Communication(port_name) as communication:
            # TODO: read device info to start working with the robot
            # refactor this
            print(f'Device Info: {communication.get_device_info()}')
            if (buffer := communication.serial_engine.read_all().decode('ISO-8859-1')):
                print(f'Previous buffer: {buffer}')

            time.sleep(5)

            robot = rc.RobotController()

            # Example usage of RobotController
            robot.send(communication, ['kbalance', 3])
            robot.send(communication, ['d', 2])

            for task in c_poses:
                print(f'task: {task}')
                robot.send(communication, ['L', task, 1])

            robot.send(communication, ['d', 2])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_ExecuteJsonRobot.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    command = read_command(file_path)
    c_poses = make_command(command)
    print(c_poses)
    execute_command(c_poses)
