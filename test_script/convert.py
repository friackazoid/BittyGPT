# Temporary script to convert the provided data to the required format

import json
from test_BittyGpt import Command, Pose, Leg

# Provided data
data = {
    "poses": [[20,  40,   0,   0,   5,   5,   3,   3,  90,  90,  45,  45, -60, -60,   5,   5]],
    "description": "playfull pose with butt up"
}

# Convert the data to the required format
poses = []
for pose in data["poses"]:
    poses.append(Pose(
        left_front=Leg(sholder=pose[8], elbow=pose[12]),
        left_back=Leg(sholder=pose[9], elbow=pose[13]),
        right_front=Leg(sholder=pose[10], elbow=pose[14]),
        right_back=Leg(sholder=pose[11], elbow=pose[15])
    ))

# Create Command object
command = Command(poses=poses, description=data["description"])

# Convert Command object to JSON
command_json = command.json()

# Print the JSON
print(command_json)
