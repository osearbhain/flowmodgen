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
A POX component to generate flow_mod messages to a switch, simulating
busy network conditions.

This version registers SwitchGenFlowMods as a Recoco Task object, with
its own run() method to do the recurring part.
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

# Create a logger for this component
log = core.getLogger()
_num_switches = 0 # global variable
#_connref          # global variable

class SendFlowMods (Task):
  """
  Sends many flow modification requests to all switches that we know
  of (Actually only doing one switch for now)
  """
  def __init__(self):
    Task.__init__(self)  # call our superconstructor

    # Note! We can't start our event loop until the core is up. Therefore, 
    # we'll add an event handler.
    core.addListener(pox.core.GoingUpEvent, self.start_run_loop)

  def start_run_loop(self, event):
    """
    Takes a second parameter: the GoingUpEvent object (which we ignore)
    """ 
    # This causes us to be added to the scheduler's recurring Task queue
    Task.start(self) 

  def run(self):
    """
    run() is the method that gets called by the scheduler to execute this task
    """
    
    _num_rules_installed = 0
    _current_working_set = 0
    global _required_working_set
    global _modsps
    global _connref
    global _num_switches
    lasttime = time.time()
    currtime = lasttime
    nummods = 0.0

    # This is where I should send flow_mod messages to any switches that I know about
    while core.running:
      if _num_switches > 0: # then it's safe to reference _connref()
        connection = _connref()
        if connection is not None: # double checking in case connection died
          currtime = time.time()
          nummods = int(currtime - lasttime) * _modsps
          if nummods >= 1:
            # Send 'nummods' number of flow_mod requests
            #print('do sendmods - nummods is %s' % (nummods))
            for i in range (1,nummods):
              # do i need to create a new msg each time?
              # - probably safer to
              # note - first rule added is rule 0. It's the first
              # deleted as well. Be careful 0-indexing doesn't
              # lead to messed up logic later
              msg = of.ofp_flow_mod()
              msg.priority = 42
              msg.cookie = _num_rules_installed
              msg.match.dl_type = 0x800
              msg.match.nw_dst = IPAddr("192.168.1.4")
              #msg.match.tp_dst = 80
              msg.hard_timeout = 600
              msg.actions.append(of.ofp_action_output(port = 4))
              connection.send(msg)
              print('adding rule # {}, nmi {}, cws {}'.format(msg.cookie, _num_rules_installed, _current_working_set))
              _current_working_set += 1
              _num_rules_installed += 1
              
              if _current_working_set > _required_working_set:
                msg = of.ofp_flow_mod()
                msg.command = of.OFPFC_DELETE
                msg.priority = 42
                msg.cookie = _num_rules_installed - _current_working_set
                msg.match.dl_type = 0x800
                msg.match.nw_dst = IPAddr("192.168.1.4")
                #msg.match.tp_dst = 80
                msg.hard_timeout = 600
                msg.actions.append(of.ofp_action_output(port = 4))
                connection.send(msg)
                print('removing rule # {}, nmi {}, cws {}'.format(msg.cookie, _num_rules_installed, _current_working_set))
                _current_working_set -= 1


            lasttime += int(currtime - lasttime)
      yield(Sleep(.01, False))
    yield False
    
  def sendmods(self, connection, nummods):
    """
    send however many flow_mod messages are required to maintain
    a particular per-second rate.
    """
    print('in sendmods - nummods is %s' % (nummods))


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
    _connref = weakref.ref(event.connection)
    global _num_switches
    _num_switches += 1
    # TODO!!!!!!!!!!!!!!!!!!!!!
    # A new switch, so add the initial 'working set' of rules, including
    # a default rule to send packets to host 3, then send a batch request
    # to make sure those are all installed before setting a flag to allow
    # the experiment to run (in 'run()' above')
    
      
def launch (modsps = 1, setsize = 1):
  """
  Sets flow_mods per second and working set to values supplied as
  arguments, or to defaults of 1 and 1 respectively.
  
  'modsps' is number of flow-mod messages to be generated per second
  and 'setsize' is the size to the working set to be maintained in
  the switch flow table.
  
  Call this component as, e.g.:
  ./pox.py flowmodgen --modsps=100 --setsize=50
  """

  # Arguments passed from the commandline are ordinarily always
  # strings, so we need to validate and convert modsps and setsize.

  try:
    global _modsps
    _modsps = int(str(modsps), 10)
    assert _modsps >= 0
  except:
    raise RuntimeError("Expected modsps to be a number")

  try:
    global _required_working_set
    _required_working_set = int(str(setsize), 10)
    assert _required_working_set >= 0
  except:
    raise RuntimeError("Expected setsize to be a number")

  core.registerNew(SendFlowMods)
  core.registerNew(SwitchHandler)
