 /*// Switch NOX application with support of QoS for CPqD/of12softswitch.
 *
 * SwitchQoS is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * SwitchQoS NOX is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with NOX.  If not, see <http://www.gnu.org/licenses/>.
 */
#include <boost/bind.hpp>
#include <boost/foreach.hpp>
#include <boost/shared_array.hpp>
#include <cstring>
#include <netinet/in.h>
#include <stdexcept>
#include <stdint.h>

#include "openflow-default.hh"
#include "assert.hh"
#include "component.hh"
#include "flow.hh"
#include "fnv_hash.hh"
#include "hash_set.hh"
#include "ofp-msg-event.hh"
#include "vlog.hh"
#include "flowmod.hh"
#include "datapath-join.hh"
#include <stdio.h>

#include <stdio.h>
#include "netinet++/ethernetaddr.hh"
#include "netinet++/ethernet.hh"

#include "../../../oflib/ofl-actions.h"
#include "../../../oflib/ofl-messages.h"

using namespace vigil;
using namespace vigil::container;
using namespace std;

namespace {

struct Mac_source
{
    /* Key. */
    datapathid datapath_id;     /* Switch. */
    ethernetaddr mac;           /* Source MAC. */

    /* Value. */
    mutable int port;           /* Port where packets from 'mac' were seen. */

    Mac_source() : port(-1) { }
    Mac_source(datapathid datapath_id_, ethernetaddr mac_)
        : datapath_id(datapath_id_), mac(mac_), port(-1)
        { }
};

bool operator==(const Mac_source& a, const Mac_source& b)
{
    return a.datapath_id == b.datapath_id && a.mac == b.mac;
}

bool operator!=(const Mac_source& a, const Mac_source& b) 
{
    return !(a == b);
}

struct Hash_mac_source
{
    std::size_t operator()(const Mac_source& val) const {
        uint32_t x;
        x = vigil::fnv_hash(&val.datapath_id, sizeof val.datapath_id);
        x = vigil::fnv_hash(val.mac.octet, sizeof val.mac.octet, x);
        return x;
    }
};

Vlog_module log("switchqos");

class SwitchQoS
    : public Component 
{
public:
    SwitchQoS(const Context* c,
           const json_object*) 
        : Component(c) { }

    void configure(const Configuration*);

    void install();

    Disposition handle(const Event&);
    //Disposition handle_dp_join(const Event& e);
private:
    typedef hash_set<Mac_source, Hash_mac_source> Source_table;
    Source_table sources;

    /* Set up a flow when we know the destination of a packet?  This should
     * ordinarily be true; it is only usefully false for debugging purposes. */
    bool setup_flows;
};

void 
SwitchQoS::configure(const Configuration* conf) {
    setup_flows = true; // default value
    BOOST_FOREACH (const std::string& arg, conf->get_arguments()) {
        if (arg == "noflow") {
            setup_flows = false;
        } else {
            VLOG_WARN(log, "argument \"%s\" not supported", arg.c_str());
        }
    }
    
    register_handler(Ofp_msg_event::get_name(OFPT_PACKET_IN), boost::bind(&SwitchQoS::handle, this, _1));
    
}

void
SwitchQoS::install() {

}

Disposition
SwitchQoS::handle(const Event& e)
{
    const Ofp_msg_event& pi = assert_cast<const Ofp_msg_event&>(e);

    struct ofl_msg_packet_in *in = (struct ofl_msg_packet_in *)**pi.msg;
    Flow *flow = new Flow((struct ofl_match*) in->match);

    /* drop all LLDP packets */
        uint16_t dl_type;
        flow->get_Field<uint16_t>("eth_type",&dl_type);
        if (dl_type == ethernet::LLDP){
            return CONTINUE;
        }
       
    uint32_t in_port;
    flow->get_Field<uint32_t>("in_port", &in_port);        
	
   
    /* Learn the source. */
    uint8_t eth_src[6];
    flow->get_Field("eth_src", eth_src);
    ethernetaddr dl_src(eth_src);
    if (!dl_src.is_multicast()) {
        Mac_source src(pi.dpid, dl_src);
        Source_table::iterator i = sources.insert(src).first;

        if (i->port != in_port) {
            i->port = in_port;
            VLOG_DBG(log, "learned that "EA_FMT" is on datapath %s port %d",
                     EA_ARGS(&dl_src), pi.dpid.string().c_str(),
                     (int) in_port);
        }
    } else {
        VLOG_DBG(log, "multicast packet source "EA_FMT, EA_ARGS(&dl_src));
    }

    /* Figure out the destination. */
    int out_port = -1;        /* Flood by default. */
    uint8_t eth_dst[6];
    flow->get_Field("eth_dst", eth_dst);
    ethernetaddr dl_dst(eth_dst);
    if (!dl_dst.is_multicast()) {
        Mac_source dst(pi.dpid, dl_dst);
	Source_table::iterator i(sources.find(dst));
        if (i != sources.end()) {
            out_port = i->port;
        }
    }
		

    /* Set up a flow if the output port is known. */
    if (setup_flows && out_port != -1) {
        
        uint8_t ip_proto;
        flow->get_Field<uint8_t>("ip_proto",&ip_proto);
//VLOG_DBG(log,"%d",ip_proto);
        bool is_tcp = (ip_proto == 6);

        uint16_t port_src;
        flow->get_Field<uint16_t>(is_tcp ? "tcp_src" : "udp_src",&port_src);
        port_src = ntohs(port_src);
        uint16_t port_dst;
        flow->get_Field<uint16_t>(is_tcp ? "tcp_dst" : "udp_dst",&port_dst);
        port_dst = ntohs(port_dst);

        uint16_t eth_type;
        flow->get_Field<uint16_t>("eth_type",&eth_type);
        //eth_type = ntohs(eth_type);
printf("eth_type=0x%x(ntohs - 0x%x, htons - 0x%x)\n",eth_type,ntohs(eth_type),htons(eth_type));
//printf("eth_type=0x%x(0x%x)\n",eth_type,htons(eth_type));

        
        uint32_t ipv4_src;
        flow->get_Field<uint32_t>("ipv4_src",&ipv4_src);
        uint32_t ipv4_dst;
        flow->get_Field<uint32_t>("ipv4_dst",&ipv4_dst);
        
	Flow  f;
	f.Add_Field("in_port", in_port);
	f.Add_Field("eth_src", eth_src);
	f.Add_Field("eth_dst",eth_dst);
    
    

	Actions *acts = new Actions();
    FlowMod *mod =
 new FlowMod(0x00ULL,0x00ULL, 0,OFPFC_ADD, 1, OFP_FLOW_PERMANENT, OFP_DEFAULT_PRIORITY,in->buffer_id, 
                                    OFPP_ANY, OFPG_ANY, ofd_flow_mod_flags());

        if (eth_type == 0x800) {
	    /* SiPP */
            /* signalization */
            if (!is_tcp && port_dst == 5060 ) {
                printf("CreateSetQueue(1)\n");
		f.Add_Field("eth_type",eth_type);
   		f.Add_Field("ip_proto",ip_proto);
                f.Add_Field("udp_dst",5060);
                mod->AddMatch(&f.match);
                acts->CreateSetQueue(1);
            }
	    /*rtp*/
	    else if (!is_tcp && port_dst == 6000 ) {
                printf("CreateSetQueue(1)\n");
		f.Add_Field("eth_type",eth_type);
   		f.Add_Field("ip_proto",ip_proto);
                f.Add_Field("udp_dst",6000);
                mod->AddMatch(&f.match);
                acts->CreateSetQueue(1);
            }
	    else if (!is_tcp && port_dst == 6002 ) {
                printf("CreateSetQueue(1)\n");
		f.Add_Field("eth_type",eth_type);
   		f.Add_Field("ip_proto",ip_proto);
                f.Add_Field("udp_dst",6002);
                mod->AddMatch(&f.match);
                acts->CreateSetQueue(1);
            }
	    /*iscsi*/
            else if (is_tcp && port_dst == 3260) {
                printf("CreateSetQueue(2)\n");
                f.Add_Field("tcp_dst",port_dst);
		f.Add_Field("eth_type",eth_type);
                f.Add_Field("ip_proto",ip_proto);
		mod->AddMatch(&f.match); 
		acts->CreateSetQueue(2);
            }
	    /*iperf*/
	    else if (is_tcp && port_dst == 5001) {
                
		printf("CreateSetQueue(3)\n");
                f.Add_Field("tcp_dst",port_dst);
		f.Add_Field("eth_type",eth_type);
                f.Add_Field("ip_proto",ip_proto);
		mod->AddMatch(&f.match);
                acts->CreateSetQueue(3);
            }
	    else	
		mod->AddMatch(&f.match);
        }
	else
	    mod->AddMatch(&f.match);


        acts->CreateOutput(out_port);
        Instruction *inst =  new Instruction();
        inst->CreateApply(acts);
	    mod->AddInstructions(inst);

        send_openflow_msg(pi.dpid, (struct ofl_msg_header *)&mod->fm_msg, 0/*xid*/, true/*block*/);
    }
    /* Send out packet if necessary. */
    if (!setup_flows || out_port == -1 || in->buffer_id == UINT32_MAX) {
        if (in->buffer_id == UINT32_MAX) {
            if (in->total_len != in->data_length) {
                /* Control path didn't buffer the packet and didn't send us
                 * the whole thing--what gives? */
                VLOG_DBG(log, "total_len=%"PRIu16" data_len=%zu\n",
                        in->total_len, in->data_length);
                return CONTINUE;
            }
            send_openflow_pkt(pi.dpid, Nonowning_buffer(in->data, in->data_length), in_port, out_port == -1 ? OFPP_FLOOD : out_port, true/*block*/);
        } else {
            send_openflow_pkt(pi.dpid, in->buffer_id, in_port, out_port == -1 ? OFPP_FLOOD : out_port, true/*block*/);
        }
    }
    return CONTINUE;
}

REGISTER_COMPONENT(container::Simple_component_factory<SwitchQoS>, SwitchQoS);

} // unnamed namespacennamed namespace
