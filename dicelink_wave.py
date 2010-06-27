# Copyright 2009, 2010 Klaus Weidner <klausw@google.com>
# 
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
# 
#        http://www.apache.org/licenses/LICENSE-2.0
# 
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from waveapi import events
from waveapi import robot
from waveapi import appengine_robot_runner
import logging

import config
import wave_ops

if __name__ == '__main__':
  myRobot = robot.Robot(config.getConfig('Name', 'dicelink'),
      image_url=config.getConfig('ImageUrl', 'http://dicelink.appspot.com/img/icon.png'),
      profile_url=config.getConfig('ProfileUrl', 'http://dicelink.appspot.com/'))
  logging.getLogger().setLevel(config.getConfig('LogLevel', logging.INFO))
  myRobot.register_handler(events.WaveletSelfAdded, wave_ops.OnRobotAdded)
  myRobot.register_handler(events.WaveletBlipRemoved, wave_ops.OnBlipDeleted, events.Context.SELF)
  myRobot.register_handler(events.FormButtonClicked, wave_ops.OnButtonClicked, events.Context.SELF)
  myRobot.register_handler(events.BlipSubmitted, wave_ops.OnBlipSubmitted, events.Context.SELF)
  myRobot.register_handler(events.GadgetStateChanged, wave_ops.OnGadgetStateChanged, events.Context.SELF)

  #myRobot.setup_oauth(credentials.CONSUMER_KEY, credentials.CONSUMER_SECRET, server_rpc_base='http://gmodules.com/api/rpc') 
  appengine_robot_runner.run(myRobot)
