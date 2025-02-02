import json
import os
import time
import sys
import signal

from typing_extensions import override
from pydantic import BaseModel

from openai import OpenAI, AssistantEventHandler
from openai.types.beta.threads import Text, TextDelta
from openai.types.beta.threads.runs import RunStep, RunStepDelta

import SerialCommunication as sc
import RobotController as rc


api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=api_key)

communication = None
robot = None


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


# def execute_command(command: Command):
#    port_name = "/dev/ttyUSB0"  # Select the first available port
#    with sc.Communication(port_name) as communication:
#        # TODO: read device info to start working with the robot
#        # refactor this
#        print(f'Device Info: {communication.get_device_info()}')
#        if (buffer := communication.serial_engine.read_all().decode('ISO-8859-1')):
#            print(f'Previous buffer: {buffer}')
#
#        time.sleep(5)
#        robot = rc.RobotController()
#
#        # Example usage of RobotController
#        robot.send(communication, ['kbalance', 1])
#        robot.send(communication, ['d', 1])
#
#        tasks = make_command(command)
#        print("Commands:")
#        print(tasks)
#        print("===============")
#
#        for task in tasks:
#            print(f'task: {task}')
#            robot.send(communication, ['L', task, 1])
#
#        robot.send(communication, ['d', 2])

def execute_command(command: Command):
    tasks = make_command(command)
    print("Commands:")
    print(tasks)
    print("===============")

    for task in tasks:
        print(f'task: {task}')
        robot.send(communication, ['L', task, 1])


class EventHandler(AssistantEventHandler):

    @override
    def on_text_created(self, text: Text) -> None:
        print(f"\n[on_text_created] assistant >", end="", flush=True)

    @override
    def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
        print(f"On text delta: {delta.value}; Snapshot: {snapshot}")

    def on_tool_call_created(self, tool_call):
        print(f"\n[on_tool_call_created] assistant > {tool_call.type}\n",
              flush=True)

    def on_tool_call_delta(self, delta, snapshot):
        print(f"\n[on_tool_call_delta] assistant > {delta.type}\n", flush=True)
        # if delta.type == "function":
        # print(f"""Function name: {delta.function.name}
        #      Arguments: {delta.function.arguments}""")

    @override
    def on_event(self, event):
        print(f"Event: {event.event}")
        if event.event == "thread.run.step.created":
            details = event.data.step_details
            print(f"Step Details: {details}")
        elif event.event == "thread.message.created":
            print(f"Message: {event.data.content} Role: {event.data.role} \n")
        elif event.event == "thread.run.requires_action":
            run_id = event.data.id
            self.handle_requires_action(event.data, run_id)

    def on_run_step_delta(self, delta: RunStepDelta, snapshot: RunStep) -> None:
        details = delta.step_details
        if details is not None and details.type == "tool_calls":
            for tool in details.tool_calls or []:
                # print(f"[on_run_step_delta] Tool: {tool}")
                if tool.type == "function":
                    print(f"Function name: {tool.function}")

    def handle_requires_action(self, data, run_id):
        # print(f"handle_ruquires_action  Data: {data}")
        tool_outputs = []

        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "execute_command":
                print(f"[handle_ruquires_action] Tool object: {tool}")
                # print(f"Arguments: {tool.function.arguments}")
                command = json.loads(tool.function.arguments)
                # print(f"Command: {command['command']}")
                execute_command(Command(**command["command"]))
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": "success"
                })

        self.submit_tool_outputs(tool_outputs, run_id)

    def submit_tool_outputs(self,  tool_outputs, run_id):
        print(f"""Submitting tool outputs: tool outputs {tool_outputs}""")
        with client.beta.threads.runs.submit_tool_outputs_stream(
                thread_id=self.current_run.thread_id,
                run_id=self.current_run.id,
                tool_outputs=tool_outputs,
                event_handler=EventHandler(),
        ) as stream:
            for text in stream.text_deltas:
                print(text, end="", flush=True)
            print()


def gpt_work(assistant_id) -> None:

    assistant = client.beta.assistants.retrieve(assistant_id)

    print(f'Model info {assistant.id}  name {assistant.name} \
            description {assistant.description} output \
            {assistant.response_format}')
    print("===============")

    thread = thread = client.beta.threads.create()

    try:
        while True:
            user_input = input("Enter your message: ")
            message = user_input
            print(f"Message: {message}")

            thread_msg = client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=message
            )

            with client.beta.threads.runs.stream(
                thread_id=thread.id,
                assistant_id=assistant.id,
                instructions="Please treat uses as dog owner. Generate json with dog-like motion for the robot.",
                tool_choice={"type": "function",
                             "function": {"name": "execute_command"}},
                event_handler=EventHandler()
            ) as stream:
                stream.until_done()

    except KeyboardInterrupt:
        print(f"""CTRL-C pressed""")
        print(f"""Stream I am DONE""")
        client.beta.threads.delete(thread.id)
        robot.send(communication, ['d', 2])


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print("Usage: python test_BittyGpt assistant_id")
        sys.exit(1)

    port_name = "/dev/ttyUSB0"  # Select the first available port
    communication = sc.Communication(port_name)

    print(f'Device Info: {communication.get_device_info()}')
    if (buffer := communication.serial_engine.read_all().decode('ISO-8859-1')):
        print(f'Previous buffer: {buffer}')

    time.sleep(5)
    robot = rc.RobotController()

    # Example usage of RobotController
    robot.send(communication, ['kbalance', 1])
    robot.send(communication, ['d', 1])

    assistant_id = sys.argv[1]
    gpt_work(assistant_id)

    robot.send(communication, ['d', 2])
    exit()
