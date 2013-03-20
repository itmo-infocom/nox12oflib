#!/usr/bin/python

from mininet.node import *
from mininet.log import setLogLevel, info, error
from mininet.net import Mininet
from mininet.topo import Topo, LinearTopo, Node
from mininet.topolib import TreeTopo
from mininet.util import createLink
from mininet.cli import CLI


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

        # Additional switch for loop topology
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

def killall():
    print "Killing ofprotocol ofdatapath nox_core"
    os.system('killall ofprotocol ofdatapath nox_core 2> /dev/null')


def test_setup1():

    killall()

    info( '*** Creating network\n' )
    net = Mininet( topo=LinearTestTopo( 3 ), switch=UserSwitchQoS, controller=RemoteController)

    #dumpNodeConnections(net.hosts)

    os.environ['NOX_CORE_DIR'] = '/usr/local/bin'
    controller = net.addController(name='c0', controller=NOX, noxArgs='switchqos')

    import networkx
    #networkx.draw(net.topo.g)
    import pylab
    #pylab.show()

    return(net)

def test_setup2():
    print "Starting 'ofdatapath -v -i eth1,eth2 punix:/var/run/s1.sock > /tmp/s1-ofd.log 2>&1 &'"
    os.system('ofdatapath -v -i eth1,eth2 punix:/var/run/s1.sock > /tmp/s1-ofd.log 2>&1 &')
    print "Starting 'ofprotocol unix:/var/run/s1.sock tcp:127.0.0.1:6633 > /tmp/s1-ofp.log 2>&1 &'"
    os.system('ofprotocol unix:/var/run/s1.sock tcp:127.0.0.1:6633 > /tmp/s1-ofp.log 2>&1 &')
    print "Starting '/usr/local/bin/nox_core --libdir=/usr/local/lib -v -i ptcp:6633 switchqos > /tmp/nox.log 2>&1 &'"
    os.system('cd /usr/local/bin/; /usr/local/bin/nox_core --libdir=/usr/local/lib -v -i ptcp:6633 switchqos > /tmp/nox.log 2>&1 &')

    while not os.path.exists('/var/run/s1.sock'):
        time.sleep(1)


def test_topology(net):

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


import paramiko

def traf_server_start(host,hosts):
    ssh=paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="openflow", password="openflow")
    #stdin, stdout, stderr = ssh.exec_command("iperf -s")
    stdin, stdout, stderr = ssh.exec_command("cd sipp-3.3; ./sipp -sn uas -i " + hosts + " -bg > ~/sipp-serv.log 2>&1 &")

    print stderr.read()

def traf_stop(host):
    ssh=paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="openflow", password="openflow")
    #stdin, stdout, stderr = ssh.exec_command("killall iperf")
    stdin, stdout, stderr = ssh.exec_command("sudo killall sipp")

def traf_client(host, hosts, hostc):
    #os.system("iperf -t 9999 -c " + hosts)
    #return
    ssh_c=paramiko.SSHClient()
    ssh_c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_c.connect(host, username="openflow", password="openflow")
    #stdin, stdout, stderr = ssh_c.exec_command("iperf -t 9999 -c " + hosts)
    # generate 1000 calls with RTP pcap playback every 10 seconds, run in background
    stdin, stdout, stderr = ssh_c.exec_command("cd sipp-3.3; sudo ./sipp -sn uac_pcap " + hosts + " -i " + hostc + " -r 130 -rp 10s -bg > ~/sipp-cl.log 2>&1 &")

    print stdout.read()
    print stderr.read()

def io_test(host):
    ssh=paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="openflow", password="openflow")
    stdin, stdout, stderr = ssh.exec_command("sudo /usr/local/bin/iscsi_test")

    #print stdout.read()
    print "Disk I/O perf: "
    #print stderr.read().splitlines()[1]
    print stderr.read()

def qos_setup(iscsi, traf):
    print "QoS: iSCSI=%d PARASITE=%d" % (iscsi, traf)
    os.system('dpctl unix:/var/run/s1.sock queue-mod 1 1 %d > /tmp/s1-queue.log' % traf)
    os.system('dpctl unix:/var/run/s1.sock queue-mod 1 2 %d >> /tmp/s1-queue.log' % iscsi)
    os.system('dpctl unix:/var/run/s1.sock queue-mod 2 1 %d >> /tmp/s1-queue.log' % traf)
    os.system('dpctl unix:/var/run/s1.sock queue-mod 2 2 %d >> /tmp/s1-queue.log' % iscsi)
    os.system('dpctl unix:/var/run/s1.sock queue-mod 1 3 %d >> /tmp/s1-queue.log' % traf)
    os.system('dpctl unix:/var/run/s1.sock queue-mod 2 3 %d >> /tmp/s1-queue.log' % traf)

def test_qos():
    from multiprocessing import Process

    paramiko.util.log_to_file('/tmp/paramiko.log')

    os.system('ifconfig eth1 down; ifconfig eth2 down')
    os.system('ifconfig eth1 up; ifconfig eth2 up')
    traf_stop('192.168.122.12')
    traf_stop('192.168.122.13')
    qos_setup(1000, 1000)
    io_test('192.168.122.11')

    #s1 = Process(target=traf_server_start, args=('10.10.10.102',))
    s1 = Process(target=traf_server_start, args=('192.168.122.12','10.10.10.102'))
    s1.start()
    #s2 = Process(target=traf_server_start, args=('10.10.10.104',))
    #s2 = Process(target=traf_server_start, args=('192.168.122.13','10.10.10.104'))
    #s2.start()
    time.sleep(15)
    #c1 = Process(target=traf_client, args=('10.10.10.102','10.10.10.104'))
    c1 = Process(target=traf_client, args=('192.168.122.13','10.10.10.102','10.10.10.104'))
    c1.start()
    #c2 = Process(target=traf_client, args=('10.10.10.104','10.10.10.102'))
    #c2 = Process(target=traf_client, args=('192.168.122.12','10.10.10.104','10.10.10.102'))
    #c2.start()

    killall()
    os.system('ifconfig eth1 down; ifconfig eth2 down')
    os.system('ifconfig eth1 up; ifconfig eth2 up')
    test_setup2()
    qos_setup(1, 1000)
    io_test('192.168.122.11')

    traf_stop('192.168.122.13')
    c1.join()
    c1.terminate()
    killall()
    os.system('ifconfig eth1 down; ifconfig eth2 down')
    os.system('ifconfig eth1 up; ifconfig eth2 up')
    test_setup2()
    c1 = Process(target=traf_client, args=('192.168.122.13','10.10.10.102','10.10.10.104'))
    c1.start()
    qos_setup(1000, 1)
    io_test('192.168.122.11')

    traf_stop('192.168.122.13')
    c1.join()
    c1.terminate()
    killall()
    os.system('ifconfig eth1 down; ifconfig eth2 down')
    os.system('ifconfig eth1 up; ifconfig eth2 up')
    test_setup2()
    c1 = Process(target=traf_client, args=('192.168.122.13','10.10.10.102','10.10.10.104'))
    c1.start()
    qos_setup(1000, 1000)
    io_test('192.168.122.11')

    traf_stop('192.168.122.13')
    c1.join()
    c1.terminate()
    killall()
    os.system('ifconfig eth1 down; ifconfig eth2 down')
    os.system('ifconfig eth1 up; ifconfig eth2 up')
    test_setup2()
    c1 = Process(target=traf_client, args=('192.168.122.13','10.10.10.102','10.10.10.104'))
    c1.start()
    qos_setup(1, 1)
    io_test('192.168.122.11')

    traf_stop('192.168.122.12')
    traf_stop('192.168.122.13')

    c1.join()
    c1.terminate()
    #c2.join()
    #c2.terminate()
    s1.terminate()
    #s2.terminate()


if __name__ == '__main__':
    import time
    import os.path
    import os
    import sys

    #from mininet.util import dumpNodeConnections
    #import matplotlib

    #setLogLevel( 'debug' )
    setLogLevel( 'info' )

    #net = test_setup()

    #start(net)
    killall()
    test_setup2()
    #qos_setup(1000, 0)

    #while 1:
    #	time.sleep(10)

    test_qos()
    killall()
    sys.exit()
    #test_topology(net)

    #CLI( net )
    #net.stop()
    #killall()
    #sys.exit()


