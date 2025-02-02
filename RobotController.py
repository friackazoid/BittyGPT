#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import SerialCommunication as sc


import logging
import struct
import threading
import time


# Configure logging
FORMAT = '%(asctime)-15s %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    filename='./logfile.log', filemode='a+', level=logging.DEBUG, format=FORMAT
)
logger = logging.getLogger(__name__)


def ensure_bytes(value):
    """Ensure that the input value is converted to bytes."""
    if isinstance(value, str):
        return value.encode('utf-8')
    return value

class RobotController:
    def __init__(self):
        self.delay_between_slices = 0.001
        self.return_value = ''
        self.logger = logging.getLogger(self.__class__.__name__)
        self.port = None

    def serial_write_num_to_byte(self, port, token, var=None):
        self.logger.debug(f'serial_write_num_to_byte, token={token}, var={var}')
        if var is None:
            var = []

        if token == 'K':
            period = var[0]
            skill_header = 4 if period > 0 else 7
            frame_size = (
                8 if period > 1 else 16 if period == 1 else 20
            )  # gait, posture, behavior
            angle_ratio = 1

            for row in range(abs(period)):
                angles = var[
                    skill_header
                    + row * frame_size : skill_header
                    + row * frame_size
                    + min(16, frame_size)
                ]
                if any(angle > 125 or angle < -125 for angle in angles):
                    angle_ratio = 2
                    break

            if angle_ratio == 2:
                var[3] = 2
                for row in range(abs(period)):
                    indices = range(
                        skill_header + row * frame_size,
                        skill_header
                        + row * frame_size
                        + min(16, frame_size),
                    )
                    for i in indices:
                        var[i] //= 2

                msg = f'rescaled: {var}'
                self.logger.debug(msg)

            var = list(map(int, var))
            in_str = token.encode() + struct.pack('b' * len(var), *var) + b'~'

        else:
            message = list(map(int, var)) if var else []
            if token.isupper():
                if token == 'B':
                    for i in range(len(message) // 2):
                        message[i * 2 + 1] *= 8  # Adjust timing for tests
                        self.logger.debug(f"{message[i*2]},{message[i*2+1]}")
                pack_type = 'B' if token in ('W', 'C') else 'b'
                in_str = (
                    token.encode()
                    + struct.pack(f'{pack_type}' * len(message), *message)
                    + b'~'
                )
            else:
                message_str = ' '.join(str(round(elem)) for elem in var)
                in_str = token.encode() + ensure_bytes(message_str) + b'\n'

        slice_index = 0
        while len(in_str) > slice_index:
            chunk = in_str[slice_index: slice_index + 20]
            port.send_data(chunk)
            slice_index += 20
            time.sleep(self.delay_between_slices)
        self.logger.debug(f'Sent data: {in_str}')

    # TODO: make port member of the class
    def _serial_write_byte(self, port, var=None):
        self.logger.info(f'serial_write_byte, var={var}')
        if var is None:
            var = []
        token = var[0][0]
        in_str = ''
        if (
            token in 'cmi but'
            and len(var) >= 2
        ):
            in_str = ' '.join(var) + '\n'
        elif token in 'LI':
            if len(var[0]) > 1:
                var.insert(1, var[0][1:])
            var[1:] = list(map(int, var[1:]))
            in_str = (
                token.encode()
                + struct.pack('b' * (len(var) - 1), *var[1:])
                + b'~'
            )
        elif token in 'wkX':
            in_str = var[0] + '\n'
        else:
            in_str = token + '\n'
        self.logger.debug(f"Sending: {in_str}")
        port.send_data(ensure_bytes(in_str))
        time.sleep(0.01)

    def print_serial_message(self, port, token, timeout=0):
        threshold = 4 if token in 'kK' else 3
        start_time = time.time()
        all_prints = ''
        while True:
            time.sleep(0.001)
            if port:
                response = port.serial_engine.readline().decode('ISO-8859-1')
                if response:
                    self.logger.debug(f"response is: {response}")
                    response_trim = response.split('\r')[0]
                    self.logger.debug(f"response_trim is: {response_trim}")
                    if response_trim.lower() == token.lower():
                        return [response, all_prints]
                    elif token == 'p' and response_trim == 'k':
                        return [response, all_prints]
                    else:
                        all_prints += response
            now = time.time()
            if (now - start_time) > threshold:
                self.logger.debug(f"Elapsed time: {threshold} seconds")
                threshold += 2
                if threshold > 5:
                    return -1
            if 0 < timeout < now - start_time:
                return -1

    # TODO: make port member of the class
    def send_task(self, port, task, timeout=0):
        self.logger.debug(f'Task: {task}')
        if port:
            try:
                if (previous_buffer := port.serial_engine.read_all().decode('ISO-8859-1')):
                    self.logger.debug(f'Previous buffer: {previous_buffer}')

                if len(task) == 2:
                    self._serial_write_byte(port, [task[0]])
                elif isinstance(task[1][0], int):
                    self.serial_write_num_to_byte(port, task[0], task[1])
                else:
                    self._serial_write_byte(port, task[1])
                token = task[0][0]
                if token in 'IL':
                    timeout = 1
                last_message = self.print_serial_message(port, token, timeout)
                time.sleep(task[-1])
            except Exception as e:
                self.logger.error(f"Error while sending task {task}: {e}")
                last_message = -1
        else:
            last_message = -1
        self.return_value = last_message
        return last_message

    @staticmethod
    def split_task_for_large_angles(task):
        """Split task for large angles."""
        token = task[0]
        queue = []
        if len(task) > 2 and token in 'LI':
            var = task[1]
            indexed_list = []

            if token == 'L':
                for i in range(4):
                    for j in range(4):
                        angle = var[4 * j + i]
                        if angle < -125 or angle > 125:
                            indexed_list += [4 * j + i, angle]
                            var[4 * j + i] = max(min(angle, 125), -125)
                if var:
                    queue.append(['L', var, task[-1]])
                if indexed_list:
                    queue[0][-1] = 0.01
                    queue.append(['i', indexed_list, task[-1]])
            elif token == 'I':
                """
                'I' indicates the command to control all joint servos
                to rotate AT THE SAME TIME (currently, the command supports
                16 degrees of freedom, that is, 16 servos). The angles are
                encoded as BINARY numbers for efficiency.
                """
                if min(var) < -125 or max(var) > 125:
                    task[0] = 'i'
                queue.append(task)
        else:
            queue.append(task)
        return queue

    def send(self, ports, task, timeout=0):
        """Send."""
        if isinstance(ports, dict):
            # return self._send_to_multiple_ports(ports, task, timeout)
            logger.error('Not implemented yet.')
        else:
            return self._send_to_single_port(ports, task, timeout)

    def _send_to_single_port(self, port, task, timeout=0):
        queue = self.split_task_for_large_angles(task)
        for task in queue:
            return_result = self.send_task(port, task, timeout)
        return return_result

    def close_serial_behavior(self, port):
        try:
            port.close_engine()
        except Exception as e:
            port.close_engine()
            raise e
        logger.info("Closed the serial port.")

    def close_all_serial(self, ports, clear_ports=True):
        if clear_ports:
            self.send(ports, ['d', 0], 1)
        for p in ports:
            t = threading.Thread(target=self.close_serial_behavior, args=(p,))
            t.start()
            t.join()
        if clear_ports:
            ports.clear()

def test_robot_controller():
    all_ports = sc.Communication.list_available_ports()
    if all_ports:
        port_name = all_ports[0][0]  # Select the first available port
        with sc.Communication(port_name) as communication:
            # TODO: read device info to start working with the robot
            # refactor this
            logger.debug(f'Device Info: {communication.get_device_info()}')

            if (buffer := communication.serial_engine.read_all().decode('ISO-8859-1')):
                logger.debug(f'Previous buffer: {buffer}')

            time.sleep (5)

            robot = RobotController()
            # Example usage of RobotController
            task = ['kbalance', 10]
            robot.send(communication, task)

            my_msg = {
                   "poses": [
[0, 0, 0, 0, 0, 0, 0, 0, 30, 30, 30, 30, 30, 30, 30, 30],
    [10, 5, -10, 5, -10, 10, -5, 10, 50, 55, 60, 65, 45, 50, -20, -25],
    [-10, -5, 10, -5, 10, -10, 5, -10, 25, 20, 30, 35, 60, 55, -15, -10],
    [5, 10, -5, 10, -5, 5, -10, 5, 45, 50, 55, 60, 30, 35, -30, -35],
    [0, 0, 0, 0, 0, 0, 0, 0, 30, 30, 30, 30, 30, 30, 30, 30]
                    ],
                    "description": "hi"
            }

            poses = my_msg['poses']

            for pose in poses:
                task = ['L', pose, 1]
                robot.send(communication, task)

            robot.send(communication, ['d', 2])


def main():
    """Small script to test the RobotController class."""
    all_ports = sc.Communication.list_available_ports()
    if all_ports:
        msg = f"""Trying to open port:
device {all_ports[0][0]}; name {all_ports[0][1]}
        """
        logger.debug(msg)
        port_name = all_ports[0][0]  # Select the first available port
        with sc.Communication(port_name) as communication:
            # TODO: read device info to start working with the robot
            # refactor this
            logger.debug(f'Device Info: {communication.get_device_info()}')

            if (buffer := communication.serial_engine.read_all().decode('ISO-8859-1')):
                logger.debug(f'Previous buffer: {buffer}')

            robot = RobotController()

            # Example usage of RobotController
            task = ['b', [10, 2], 4]
            robot.send(communication, task)

            task = ['L',
                   [0, 0, 0, 0, 0, 0, 0, 0,
                    45,  45, 105, 105, 45, 45, -45, -45], # sit
                    1]
            robot.send(communication, task)

            task = ['L',
                   [0, 0, 0, 0, 0, 0, 0, 0,
                    50,  50, 110, 110, 50, 50, -50, -50], # sit
                    1]
            robot.send(communication, task)

            task = ['L',
                   [0, 0, 0, 0, 0, 0, 0, 0,
                    45,  45, 105, 105, 45, 45, -45, -45], # sit
                    1]
            robot.send(communication, task)

            task = ['d', 2]
            robot.send(communication, task)

    else:
        logger.error('No port available.')
        return


if __name__ == '__main__':
    # main()
    test_robot_controller()
