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

  # ../secrets/*.py
  #myRobot.setup_oauth(credentials.CONSUMER_KEY, credentials.CONSUMER_SECRET, server_rpc_base='http://gmodules.com/api/rpc') 
  appengine_robot_runner.run(myRobot)
