#!/usr/bin/env python3
#
# Copyright (C) 2021 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os

from sys import exit

from vyos.config import Config
from vyos.configdict import dict_merge
from vyos.configverify import verify_route_maps
from vyos.configverify import verify_interface_exists
from vyos.template import render
from vyos.template import render_to_string
from vyos.util import call
from vyos.util import dict_search
from vyos.xml import defaults
from vyos import ConfigError
from vyos import frr
from vyos import airbag
airbag.enable()

config_file = r'/tmp/ospf.frr'
frr_daemon = 'ospfd'

DEBUG = os.path.exists('/tmp/ospf.debug')
if DEBUG:
    import logging
    lg = logging.getLogger("vyos.frr")
    lg.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    lg.addHandler(ch)

def get_config(config=None):
    if config:
        conf = config
    else:
        conf = Config()
    base = ['protocols', 'ospf']
    ospf = conf.get_config_dict(base, key_mangling=('-', '_'), get_first_key=True)

    # Bail out early if configuration tree does not exist
    if not conf.exists(base):
        return ospf

    # We have gathered the dict representation of the CLI, but there are default
    # options which we need to update into the dictionary retrived.
    default_values = defaults(base)

    # We have to cleanup the default dict, as default values could enable features
    # which are not explicitly enabled on the CLI. Example: default-information
    # originate comes with a default metric-type of 2, which will enable the
    # entire default-information originate tree, even when not set via CLI so we
    # need to check this first and probably drop that key.
    if dict_search('default_information.originate', ospf) is None:
        del default_values['default_information']
    if dict_search('area.area_type.nssa', ospf) is None:
        del default_values['area']['area_type']['nssa']
    if 'mpls_te' not in ospf:
        del default_values['mpls_te']
    for protocol in ['bgp', 'connected', 'kernel', 'rip', 'static']:
        if dict_search(f'redistribute.{protocol}', ospf) is None:
            del default_values['redistribute'][protocol]
    # XXX: T2665: we currently have no nice way for defaults under tag nodes,
    # clean them out and add them manually :(
    del default_values['neighbor']
    del default_values['area']['virtual_link']
    del default_values['interface']

    # merge in remaining default values
    ospf = dict_merge(default_values, ospf)

    if 'neighbor' in ospf:
        default_values = defaults(base + ['neighbor'])
        for neighbor in ospf['neighbor']:
            ospf['neighbor'][neighbor] = dict_merge(default_values, ospf['neighbor'][neighbor])

    if 'area' in ospf:
        default_values = defaults(base + ['area', 'virtual-link'])
        for area, area_config in ospf['area'].items():
            if 'virtual_link' in area_config:
                print(default_values)
                for virtual_link in area_config['virtual_link']:
                    ospf['area'][area]['virtual_link'][virtual_link] = dict_merge(
                        default_values, ospf['area'][area]['virtual_link'][virtual_link])

    if 'interface' in ospf:
        default_values = defaults(base + ['interface'])
        for interface in ospf['interface']:
            ospf['interface'][interface] = dict_merge(default_values,
                ospf['interface'][interface])

    # We also need some additional information from the config, prefix-lists
    # and route-maps for instance. They will be used in verify()
    base = ['policy']
    tmp = conf.get_config_dict(base, key_mangling=('-', '_'))
    # Merge policy dict into OSPF dict
    ospf = dict_merge(tmp, ospf)

    return ospf

def verify(ospf):
    if not ospf:
        return None

    verify_route_maps(ospf)

    if 'interface' in ospf:
        for interface in ospf['interface']:
            verify_interface_exists(interface)

    return None

def generate(ospf):
    if not ospf:
        ospf['new_frr_config'] = ''
        return None

    # render(config) not needed, its only for debug
    render(config_file, 'frr/ospf.frr.tmpl', ospf)
    ospf['new_frr_config'] = render_to_string('frr/ospf.frr.tmpl', ospf)

    return None

def apply(ospf):
    # Save original configuration prior to starting any commit actions
    frr_cfg = frr.FRRConfig()
    frr_cfg.load_configuration(frr_daemon)
    frr_cfg.modify_section(r'interface \S+', '')
    frr_cfg.modify_section('router ospf', '')
    frr_cfg.add_before(r'(ip prefix-list .*|route-map .*|line vty)', ospf['new_frr_config'])

    # Debugging
    if DEBUG:
        from pprint import pprint
        print('')
        print('--------- DEBUGGING ----------')
        pprint(dir(frr_cfg))
        print('Existing config:\n')
        for line in frr_cfg.original_config:
            print(line)
        print(f'Replacement config:\n')
        print(f'{ospf["new_frr_config"]}')
        print(f'Modified config:\n')
        print(f'{frr_cfg}')

    frr_cfg.commit_configuration(frr_daemon)

    # If FRR config is blank, rerun the blank commit x times due to frr-reload
    # behavior/bug not properly clearing out on one commit.
    if ospf['new_frr_config'] == '':
        for a in range(5):
            frr_cfg.commit_configuration(frr_daemon)

    return None

if __name__ == '__main__':
    try:
        c = get_config()
        verify(c)
        generate(c)
        apply(c)
    except ConfigError as e:
        print(e)
        exit(1)
