# Copyright 2016 Jonathan Sherwin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A POX component to generate flow_mod messages to a switch,
simulating busy network conditions.

This version registers SendFlowMods as a Recoco Task
object, with its own run() method to do the recurring part.
"""

# Import some POX stuff
from pox.core import core                     # Main POX object
import pox.openflow.libopenflow_01 as of      # OpenFlow 1.0 library
import pox.lib.packet as pkt                  # Packet parsing/construction
from pox.lib.addresses import EthAddr, IPAddr # Address types
import pox.lib.util as poxutil                # Various util functions
from pox.lib.revent import *               # Event library
from pox.lib.recoco import *               # Multitasking library
import weakref
import time
# Create a logger for this component
log = core.getLogger()
_num_switches = 0 # global variable
#_connref          # global variable

class SendFlowMods (Task):
  """
  Sends many flow modification requests to all switches that
  we know of (Actually assuming one switch for now, not
  tested for multiple switches)
  """
  def __init__(self):
    Task.__init__(self)  # call our superconstructor

    # Note! We can't start our event loop until the core is up. Therefore, 
    # we'll add an event handler.
    core.addListener(pox.core.GoingUpEvent, self.start_run_loop)

  def start_run_loop(self, event):
    """
    Takes a second parameter: the GoingUpEvent object (which
    we ignore)
    """ 
    # This causes us to be added to the scheduler's recurring Task queue
    Task.start(self) 

  def run(self):
    """
    run() is the method that gets called by the scheduler to
    execute this task
    """
    
    _num_rules_installed = 0
    _current_working_set = 0
    global _prepop
    global _num_switches
    global _barrierexpected
    global _bcount
    global _bps
    global _nwb
        
    while core.running and (_num_switches < 1):
      yield(Sleep(.1, False))

    print('switch found, running')
    global _starttime
    _starttime = time.time()
    currtime = _starttime

    # This is where I should send flow_mod messages to any switches that I know about
    while core.running and (_num_rules_installed < _bcount):
      if _num_switches > 0: # then it's safe to reference _connref()
        connection = _connref()
        #print('checking connection')
        if connection is not None: # double checking in case connection died
          #print('connection ok')
          currtime = time.time()
          rulesneeded = int((currtime - _starttime) * float(_bps)) - _num_rules_installed
          if ( rulesneeded >= 1 ) and ((_nwb > 0) or not _barrierexpected):
            if rulesneeded > 1:
              print('rulesneeded is %s' % (rulesneeded))
            # Remove an old rule from the switch
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_DELETE
            msg.priority = 42
            msg.match.dl_type = 0x800
            msg.match.nw_dst = IPAddr("192.168.1.3")
            msg.match.nw_proto=17
            msg.match.tp_dst = _bpn + _num_rules_installed
            msg.hard_timeout = 600
            msg.actions.append(of.ofp_action_output(port = 3))
            connection.send(msg)

            # Add a new rule to the switch
            msg = of.ofp_flow_mod()
            msg.priority = 42
            msg.match.dl_type = 0x800
            msg.match.nw_dst = IPAddr("192.168.1.3")
            msg.match.nw_proto=17
            msg.match.tp_dst = _bpn + _prepop + _num_rules_installed
            msg.hard_timeout = 600
            msg.actions.append(of.ofp_action_output(port = 3))
            connection.send(msg)
            _num_rules_installed += 1
            
            # Send barrier request and record time sent
            msg = of.ofp_barrier_request()
            msg.xid = _bpn + _prepop + _num_rules_installed
            global _outfile
            _outfile.write(str(currtime - _starttime) + '\t' + str(msg.xid) + '\tS\n')
            connection.send(msg)
            _barrierexpected = True
            #print('batch done, barrier requested at time {}'.format(time.time()))

      yield(Sleep(.001, False))
    print('batches all done, ready to finish')
    yield False

class SwitchHandler (object):
  """
  Waits for OpenFlow switches to connect and keeps a note of the
  connection for each of them.
  (Actually only doing one switch for now)
  """
  
  def __init__ (self):
    """
    Initialize
    """
    core.openflow.addListeners(self)

  def _handle_ConnectionUp (self, event):
    """
    Switch connected - keep track of it by adding to global list
    """
    log.debug("Connection %s" % (event.connection,))
    print("in ConnectionUp")
    global _connref
    _connref = weakref.ref(event.connection) # Should really be adding to
                                             # a list of active connections
    global _num_switches
    _num_switches += 1
    
    global _prepop
    global _bpn
    # Add default rule first
    msg = of.ofp_flow_mod()
    msg.priority = 42
    msg.actions.append(of.ofp_action_output(port = 2))
    event.connection.send(msg)
    
    # Prepopulate switch table with a specific number of rules
    for i in range (0,_prepop):
      # Creating a new msg each time, thinking that's safest.
      msg = of.ofp_flow_mod()
      msg.priority = 42
      msg.match.dl_type = 0x800
      msg.match.nw_dst = IPAddr("192.168.1.3")
      msg.match.nw_proto=17
      msg.match.tp_dst = _bpn + i
      msg.hard_timeout = 600
      msg.actions.append(of.ofp_action_output(port = 3))
      event.connection.send(msg)
      print('adding prepop rule # {}'.format(i))

    msg = of.ofp_barrier_request()
    msg.xid = _bpn + _prepop
    event.connection.send(msg)
    global _starttime
    _starttime = time.time()
    global _outfile
    _outfile.write('0\t' + str(_bpn + _prepop) + '\tS\n')
    global _barrierexpected
    _barrierexpected = True
    
  def _handle_BarrierIn(self, event):
    currtime = time.time()
    #print('barrier received at %s' % currtime)
    global _outfile
    _outfile.write(str(currtime - _starttime) + '\t' + str(event.ofp.xid) + '\tR\n')
    global _barrierexpected
    _barrierexpected = False
    
      
def launch (prepop = 1, bcount = 1, bps = 1, bpn = 1, nwb = 1):
  """  
  'prepop' is the number of rules with which a switch table should be
  prepopulated. 'bcount' is the number of batches of rule updates to be
  applied, each batch having one rule deletion and one rule addition.
  'bps' is number of batches to be generated per second. 'bpn' is base
  port number - in order to keep rules unique, the destination port
  number is incremented for each rule added. 'nwb' is a flag to direct
  us to not wait for barrier replies to come back before sending the
  next batch. 
  
  Call this component as, e.g.:
  ./pox.py flowmodgen --prepop=300 --bcount=500 --bps=50 --bpn=44000 --nwb=1
  """

  # Arguments passed from the commandline are ordinarily string type,
  # so we need to validate and convert to integer.

  try:
    global _prepop
    _prepop = int(str(prepop), 10)
    assert _prepop >= 0
  except:
    raise RuntimeError("Expected prepop to be a number")

  try:
    global _bcount
    _bcount = int(str(bcount), 10)
    assert _bcount >= 0
  except:
    raise RuntimeError("Expected bcount to be a number")

  try:
    global _bps
    _bps = int(str(bps), 10)
    assert _bps >= 0
  except:
    raise RuntimeError("Expected bps to be a number")

  try:
    global _bpn
    _bpn = int(str(bpn), 10)
    assert _bpn >= 0
  except:
    raise RuntimeError("Expected bps to be a number")

  try:
    global _nwb
    _nwb = int(str(nwb), 10)
    assert _nwb >= 0
  except:
    raise RuntimeError("Expected nwb to be a number")

  global _num_switches
  _num_switches = 0
 
  global _outfile
  filename = "fmgresults-" + time.strftime("%Y-%m-%d-%H%M%S" + ".txt")
  _outfile = open(filename, 'w')
  _outfile.write('Parameters:\nprepop\tbcount\tbps\tbpn\tnwb\n')
  _outfile.write('{}\t{}\t{}\t{}\t{}\n\n'.format(_prepop, _bcount, _bps, _bpn, _nwb))
  _outfile.write('Time\tXid\tSent/Received\n')
  

  core.registerNew(SendFlowMods)
  core.registerNew(SwitchHandler)
