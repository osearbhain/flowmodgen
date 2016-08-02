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

This version uses Recoco.Timer to schedule 'send_flow_mods' as a recurring
task.
"""

# Import some POX stuff
from pox.core import core                     # Main POX object
import pox.openflow.libopenflow_01 as of      # OpenFlow 1.0 library
import pox.lib.packet as pkt                  # Packet parsing/construction
from pox.lib.addresses import EthAddr, IPAddr # Address types
import pox.lib.util as poxutil                # Various util functions
import pox.lib.revent as revent               # Event library
import pox.lib.recoco as recoco               # Multitasking library
#from pox.lib.recoco import Timer

# Create a logger for this component
log = core.getLogger()
_current_working_set = 0 # global variable
_num_rules_installed = 0 # global variable

class flowmodgenswitch (object):
  """
  The object associated with sending flow_mod messages to a single switch.
  """
  
  def __init__ (self, connection):
    # Switch we'll be send flow_mod messages to
    self.connection = connection
 
    # Our table
    self.macToPort = {}

    # We want to hear PacketIn messages, so we listen
    # to the connection
    connection.addListeners(self)
    recoco.Timer(0.1, send_flow_mods, recurring = True, args = [connection])
 
  def _handle_PacketIn (self, event):
    """
    Handle packet in messages from the switch to implement above algorithm.
    """
    print('packet arrived')

class flowmodgen (object):
  """
  Waits for OpenFlow switches to connect and starts sending flow_mod messages
  to them.
  """
  
  def __init__ (self):
    """
    Initialize
    """
    core.openflow.addListeners(self)

  def _handle_ConnectionUp (self, event):
    """
    Switch connected - start sending...
    """
    log.debug("Connection %s" % (event.connection,))
    flowmodgenswitch(event.connection)


def launch (modsps = 1, setsize = 1):
  """
  Sets flow_mods per second and working set to values supplied as
  arguments, or to defauls of 1 and 1 respectively.
  
  'modsps' is number of flow-mod messages to be generated per second
  and 'setsize' is the size to the working set to be maintained in
  the switch flow table.
  
  Call this component as, e.g.:
  ./pox.py flowmodgen --modsps=100 --setsize=50
  """

  # Arguments passed from the commandline are ordinarily always
  # strings, so we need to validate and convert modsps and setsize.

  try:
    global _imodsps
    _imodsps = int(str(modsps), 10)
    assert _imodsps >= 0
  except:
    raise RuntimeError("Expected modsps to be a number")

  try:
    global _required_working_set
    _required_working_set = int(str(setsize), 10)
    assert _required_working_set >= 0
  except:
    raise RuntimeError("Expected setsize to be a number")

  core.registerNew(flowmodgen)
                   
def send_flow_mods (connection):
  """
  Sends a specific number of flow_mod messages to install rules
  Sends enough additional flow_mod messages to deleted previously
  installed rules in order to make sure the current working set
  of rules does not exceed the number specified by the user.
  
  Not sure if this will work for multiple switches. Global variables
  could be a problem.
  
  Algorithm:
    - while (num_rules_installed / seconds_elapsed < installation_rate)
    -   add_rule(sequence num?, priority, don't timeout)
    -   num_rules_installed++
    -   current_working_set++
    -   if (current_working_set > required_working_set)
    -     del_rule(num_rules_installed - current_working_set)
    -     current_working_set--
    -     send_barrier
  """
  global _current_working_set
  global _required_working_set
  global _num_rules_installed
  
  # Not doing the specific number thing yet, just trying to send flow_mod
  # msg to switch
  msg = of.ofp_flow_mod()
  msg.priority = 42
  msg.cookie = _num_rules_installed
  msg.match.dl_type = 0x800
  msg.match.nw_dst = IPAddr("192.168.1.4")
  #msg.match.tp_dst = 80
  msg.hard_timeout = 600
  msg.actions.append(of.ofp_action_output(port = 4))
  connection.send(msg)
  _current_working_set += 1
  _num_rules_installed += 1
  print('current_working_set %s' % (_current_working_set))


  print('Sent a flow_mod for connection %s' % (connection,))
