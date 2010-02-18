import logging

from waveapi import events
from waveapi import robot

import config
import wave_ops

VERSION='15'

if __name__ == '__main__':
  myRobot = robot.Robot(config.getConfig('Name', 'dicelink'),
      image_url=config.getConfig('ImageUrl', 'http://dicelink.appspot.com/img/icon.png'),
      version=config.getConfig('Version', VERSION),
      profile_url=config.getConfig('ProfileUrl', 'http://dicelink.appspot.com/'))
  logging.getLogger().setLevel(config.getConfig('LogLevel', logging.INFO))
  myRobot.RegisterHandler(events.WAVELET_SELF_ADDED, wave_ops.OnRobotAdded)
  myRobot.RegisterHandler(events.BLIP_SUBMITTED, wave_ops.OnBlipSubmitted)
  myRobot.RegisterHandler(events.BLIP_DELETED, wave_ops.OnBlipDeleted)

  # ../secrets/*.py
  #myRobot.setup_oauth(credentials.CONSUMER_KEY, credentials.CONSUMER_SECRET, server_rpc_base='http://gmodules.com/api/rpc') 

  myRobot.Run()
