#!/usr/bin/python

from mininet.node import *
from mininet.topo import Topo, Node


class UserSwitchQoS( UserSwitch ):
    "User-space QoS-enabled switch."

    def setQueue( self, port, queue, bandwidth):
        """Adds/modifies queue.
           port: port number
           queue: queue number
           bandwidth: bandwidth value"""
        cmd = 'dpctl unix:/var/run/' + self.name + '.sock queue-mod %d %d %d' % (port, queue, bandwidth)
        print "setQueue: '%s'" % cmd
	return quietRun( cmd )

    def getQueue( self, port):
        """Get queue configuration.
           port: port number"""
        cmd = 'dpctl unix:/var/run/' + self.name + '.sock queue-get-config %d' % port
        print "getQueue: '%s'" % cmd
        result = quietRun( cmd )
        result = re.findall('q_cnf_repl\{port="(\d+)" queues=\[\{q="(\d+)", props=\[minrate\{rate="(\d+)"\}\]\}\]\}', result)
        queues = {}
        for port, q, minrate in result:
            queues[port] = []
            queues[port].append({'q': q, 'minrate': minrate})

        return queues

    def statQueue( self, port=None, queue=None):
        """Get queue statistics.
           port: port number
           queue: queue number"""
        cmd = 'dpctl unix:/var/run/' + self.name + '.sock stats-queue'
        if port:
            cmd += ' %d' % port
        if queue:
            cmd += ' %d' % queue

        stats = {}
        print "statQueue: '%s'" % cmd
        result = quietRun( cmd )
        result = re.findall('stat_repl\{type="queue", flags="0x0", stats=\[\{(.*)\}\]\}', result)
        if len(result) and len(result[0]):
            result = result[0].split('}, {')
        for stat in result:
            port, q, tx_bytes, tx_pkt, tx_err = re.findall('port="(\d+)", q="(\d+)", tx_bytes="(\d+)", tx_pkt="(\d+)", tx_err="(\d+)"',stat)[0]
            if not stats.has_key('port'):
                stats[port] = {}
            if not stats[port].has_key('q'):
                stats[port][q] = {}
            stats[port][q] = {'tx_bytes':tx_bytes , 'tx_pkt':tx_pkt, 'tx_err':tx_err}

        return stats

    def start( self, controllers ):
        """Start OpenFlow reference user datapath.
           Log to /tmp/sN-{ofd,ofp}.log.
           controllers: list of controller objects"""
        controller = controllers[ 0 ]
        ofdlog = '/tmp/' + self.name + '-ofd.log'
        ofplog = '/tmp/' + self.name + '-ofp.log'
        self.cmd( 'ifconfig lo up' )
        mac_str = ''
        if self.defaultMAC:
            # ofdatapath expects a string of hex digits with no colons.
            mac_str = ' -d ' + ''.join( self.defaultMAC.split( ':' ) )
        intfs = sorted( self.intfs.values() )
        if self.inNamespace:
            intfs = intfs[ :-1 ]
        #self.cmd( 'ofdatapath -i ' + ','.join( intfs ) +
        self.cmd( 'ofdatapath -v -i ' + ','.join( intfs ) +
            ' punix:/var/run/' + self.name + '.sock'
                + ' 1> ' + ofdlog + ' 2> ' + ofdlog + ' &' )    
        #self.cmd( 'ofprotocol -v unix:/var/run/' + self.name +
        self.cmd( 'ofprotocol unix:/var/run/' + self.name +
            '.sock tcp:%s:%d' % ( controller.IP(), controller.port )+
            ' 1> ' + ofplog + ' 2>' + ofplog + ' &' ) 

class LinearTestTopo( Topo ):
    "Topology for a string of 2 hosts and N switches."

    def __init__( self, N ):

        # Add default members to class.
        super( LinearTestTopo, self ).__init__()

        # Create switch and host nodes
        hosts = ( 1, N + 3 )
        print "hosts: " + `hosts`
        switches = range( 2 , N + 2 )
        print "switches: " + `switches`
        for h in hosts:
            self.add_node( h, Node( is_switch=False ) )
        for s in switches:
            self.add_node( s, Node( is_switch=True ) )

        # Wire up switches
        for s in switches[ :-1 ]:
            self.add_edge( s, s + 1 )

        # Wire up hosts
        self.add_edge( hosts[ 0 ], switches[ 0 ] )
        self.add_edge( hosts[ 1 ], switches[ N - 1 ] )

        self.add_node( N + 4, Node( is_switch=True ) )
        self.add_edge( N + 4, 2)
        self.add_edge( N + 4, N + 1)

        # Consider all switches and hosts 'on'
        self.enable_all()

def start(net):
    net.start()

    for switch in net.switches:
        while not os.path.exists('/var/run/' + switch.name + '.sock'):
             time.sleep(1)

    for switch in net.switches:
        for i in switch.intfs.values():
            switch.updateMAC(i)
        #print switch.name + ": " + `switch.macs`


if __name__ == '__main__':
    import time
    import os.path
    import os
    import sys

    from mininet.log import setLogLevel, info, error
    from mininet.net import Mininet
    from mininet.topo import LinearTopo
    from mininet.topolib import TreeTopo
    from mininet.util import createLink

    from mininet.cli import CLI

    #from mininet.util import dumpNodeConnections
    import matplotlib

    #setLogLevel( 'debug' )
    setLogLevel( 'info' )

    print "Killing ofprotocol ofdatapath"
    os.system('killall ofprotocol ofdatapath')

    info( '*** Creating network\n' )
    #net = Mininet( topo=TreeTopo( depth=1, fanout=2 ), switch=UserSwitchQoS, controller=RemoteController)
    #net = Mininet( topo=TreeTopo( depth=1, fanout=3 ), switch=UserSwitchQoS, controller=RemoteController)
    #net = Mininet( topo=TreeTopo( depth=2, fanout=3 ), switch=UserSwitchQoS, controller=RemoteController)
    #net = Mininet( topo=LinearTopo( k=2 ), switch=UserSwitchQoS, controller=RemoteController)
    net = Mininet( topo=LinearTestTopo( 3 ), switch=UserSwitchQoS, controller=RemoteController)

    #dumpNodeConnections(net.hosts)

#    switch = net.addSwitch('s5')
#    net.switches[0].linkTo( switch )
#    net.switches[1].linkTo( switch )

    import networkx
    networkx.draw(net.topo.g)
    import pylab
    #pylab.show()

    
    #ni = net.topo.node_info[ net.topo.g.nodes[7]]
    #ni = net.topo.node_info[7]
    #ni.power_on = False

    start(net)
    #CLI( net )
    #sys.exit()

    print "Testing network connectivity"
    #net.ping([net.hosts[0],net.hosts[1]])
    net.pingAll()

    print "Stopping of " + net.switches[3].name
    net.configLinkStatus(net.switches[3].name, net.switches[0].name, 'down')
    net.configLinkStatus(net.switches[3].name, net.switches[2].name, 'down')
    #net.switches[3].stop()
    #time.sleep(30)
    net.hosts[0].cmd("ping -w 15 10.0.0.6")
    net.pingAll()
    print "Testing bandwidth between h1 and h2"
    net.iperf(net.hosts)
    print "Stopping of " + net.switches[1].name
    #net.switches[1].stop()
    net.configLinkStatus(net.switches[1].name, net.switches[0].name, 'down')
    net.configLinkStatus(net.switches[1].name, net.switches[2].name, 'down')
    #time.sleep(30)
    net.hosts[0].cmd("ping -w 15 10.0.0.6")
    net.pingAll()
    print "Starting of " + net.switches[3].name
    net.configLinkStatus(net.switches[3].name, net.switches[0].name, 'up')
    net.configLinkStatus(net.switches[3].name, net.switches[2].name, 'up')
    #time.sleep(30)
    net.hosts[0].cmd("ping -w 15 10.0.0.6")
    net.pingAll()
    print "Testing bandwidth between h1 and h2"
    net.iperf(net.hosts)
    print "Starting all switches"
    net.configLinkStatus(net.switches[1].name, net.switches[0].name, 'up')
    net.configLinkStatus(net.switches[1].name, net.switches[2].name, 'up')
    net.hosts[0].cmd("ping -w 15 10.0.0.6")
    net.pingAll()
    print "Testing bandwidth between h1 and h2"
    net.iperf(net.hosts)

    CLI( net )
    sys.exit()

    print "Testing bandwidth between h3 and h4"
    net.iperf(net.hosts)
    #net.stop()

    CLI( net )
    net.stop()
    sys.exit()

    info('*** statQueue', switch.statQueue(), '\n')
    info('*** setQueue(1,1,5)\n')
    switch.setQueue(1,1,5)
    info('*** getQueue(1)', switch.getQueue(1), '\n')
    info('*** setQueue(3,1,5)\n')
    switch.setQueue(3,1,5)
    info('*** getQueue(3)', switch.getQueue(3), '\n')
    info('*** setQueue(1,2,300)\n')
    switch.setQueue(1,2,300)
    info('*** getQueue(1)', switch.getQueue(1), '\n')
    info('*** setQueue(2,1,30)\n')
    switch.setQueue(2,1,30)
    info('*** getQueue(2)', switch.getQueue(2), '\n')
    info('*** setQueue(2,2,1000)\n')
    switch.setQueue(2,2,1000)
    info('*** getQueue(2)', switch.getQueue(2), '\n')
    info('*** setQueue(3,2,1000)\n')
    switch.setQueue(3,2,1000)
    info('*** getQueue(3)', switch.getQueue(3), '\n')
    info('*** statQueue', switch.statQueue(), '\n')

    CLI( net )
    net.stop()

