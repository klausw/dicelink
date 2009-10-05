import re

from waveapi import document
from waveapi import events
from waveapi import model
from waveapi import robot

import persist
import roll

VERSION='7'

def OnRobotAdded(properties, context):
  """Invoked when the robot has been added."""
  root_wavelet = context.GetRootWavelet()
  root_wavelet.CreateBlip().GetDocument().SetText('DiceLink v%s joined.' % VERSION)

def SetTextWithAttributes(doc, start, end, texts):
  old_len = end - start 
  new_text = ''.join([p[0] for p in texts])
  doc.SetTextInRange(document.Range(start, end), new_text)
  for text, anno, val in texts:
    doc.SetAnnotation(document.Range(start, start+len(text)), anno, val)
    start += len(text)
  return len(new_text) - old_len

def OnBlipSubmitted(properties, context):
  """Invoked when a blip was submitted."""
  blip = context.GetBlipById(properties['blipId'])
  creator = blip.GetCreator()
  doc = blip.GetDocument()
  txt = doc.GetText()
  out = []
  offset = 0
  for spec in roll.GetRollMatches(txt):
    num, detail = roll.RollDice(spec)
    match_start = spec['start'] +offset
    match_end = spec['end'] + offset
    offset += SetTextWithAttributes(doc, match_start, match_end, [
      (spec['spec'], 'style/color', '#aa00ff'),
      ('=%d' % num, 'style/fontWeight', 'bold'),
      (' [%s]' % detail, 'style/color', 'gray'),
    ])
    #out.append('%s rolled %s: %d [%s]' % (creator, spec['spec'], num, detail))
    persist.SaveMsg(creator, 'rolled %s: %d [%s]' % (spec['spec'], num, detail))
  if out:
    root_wavelet = context.GetRootWavelet()
    root_wavelet.CreateBlip().GetDocument().SetText('\n'.join(out))

if __name__ == '__main__':
  myRobot = robot.Robot('dicelink', 
      image_url='http://dicelink.appspot.com/img/icon.png',
      version=VERSION,
      profile_url='http://dicelink.appspot.com/')
  myRobot.RegisterHandler(events.WAVELET_SELF_ADDED, OnRobotAdded)
  myRobot.RegisterHandler(events.BLIP_SUBMITTED, OnBlipSubmitted)
  myRobot.Run()
