#!/Library/Frameworks/Python.framework/Versions/2.7/Resources/Python.app/Contents/MacOS/Python

import sys
import os
import shutil
import argparse
from distutils.sysconfig import get_python_lib
import yaml
from jnpr.jsnap.snap import Parse
from jnpr.jsnap.check import Comparator
from jnpr.jsnap.notify import Notification
from threading import Thread
from jnpr.junos import Device
import distutils.dir_util


class Jsnap:

    # taking parameters from command line
    def __init__(self):
        self.parser = argparse.ArgumentParser()
        group = self.parser.add_mutually_exclusive_group()
        # for mutually exclusive gp, can not use both options
        group.add_argument(
            '--snap',
            action='store_true',
            help="take the snapshot")
        group.add_argument(
            '--check',
            action='store_true',
            help=" compare snapshots")
        group.add_argument(
            '--snapcheck',
            action='store_true',
            help='check current snapshot')
        group.add_argument(
            "--init",
            action="store_true",
            help="init file",
        )
        group.add_argument(
            "--diff",
            action="store_true",
            help="display difference between two snapshots"
        )

        self.parser.add_argument(
            "pre_snapfile",
            nargs='?',
            help="pre snapshot filename")       # make it optional
        self.parser.add_argument(
            "post_snapfile",
            nargs='?',
            help="post snapshot filename",
            type=str)       # make it optional
        self.parser.add_argument(
            "-f", "--file",
            help="config file to take snapshot",
            type=str)
        self.parser.add_argument("-t", "--hostname", help="hostname", type=str)
        self.parser.add_argument(
            "-p",
            "--passwd",
            help="password to login",
            type=str)
        self.parser.add_argument(
            "-l",
            "--login",
            help="username to login",
            type=str)
        self.parser.add_argument(
            "-m",
            "--mail",
            help="mail result to given id",
            type=str)
        self.parser.add_argument(
            "-o",
            "--overwrite",
            action='store_true',
            help="over directories and files generated by init",
        )

        self.args = self.parser.parse_args()

        if len(sys.argv) == 1:
            self.parser.print_help()
            sys.exit(1)

    # call hosts class, connect hosts and get host list
    # use pre_snapfile because always first file is pre_snapfile regardless of
    # its name
    def get_hosts(self):
        output_file = self.args.pre_snapfile
        conf_file = self.args.file
        config_file = open(conf_file, 'r')
        self.main_file = yaml.load(config_file)
        self.login(output_file)

    # call to generate snap files
    def generate_rpc_reply(self, dev, snap_files):
        test_files = []
        for tfile in self.main_file['tests']:
            filepath = os.path.join(os.getcwd(), 'configs', tfile)
            test_file = open(filepath, 'r')
            test_files.append(yaml.load(test_file))
        g = Parse()
        for tests in test_files:
            g.generate_reply(tests, dev, snap_files)

    # called by check and snapcheck argument, to compare snap files
    def compare_tests(self, hostname):
        comp = Comparator()
        chk = self.args.check
        diff = self.args.diff
        if (chk or diff):
            test_obj = comp.generate_test_files(
                self.main_file,
                hostname,
                chk,
                diff,
                self.args.pre_snapfile,
                self.args.post_snapfile)
        else:
            test_obj = comp.generate_test_files(
                self.main_file,
                hostname,
                chk,
                diff,
                self.args.pre_snapfile)
        return test_obj

    def login(self, output_file):
        self.host_list = []
        if self.args.hostname is None:
            k = self.main_file['hosts'][0]
            # when group of devices are given, searching for include keyword in
            # hosts in main.yaml file
            if k.__contains__('include'):
                lfile = k['include']
                login_file = open(lfile, 'r')
                dev_file = yaml.load(login_file)
                gp = k['group']

                dgroup = [i.strip() for i in gp.split(',')]
                for dgp in dev_file:
                    if dgroup[0] == 'all' or dgp in dgroup:
                        for val in dev_file[dgp]:
                            hostname = val.keys()[0]
                            self.host_list.append(hostname)
                            username = val[hostname]['username']
                            password = val[hostname]['passwd']
                            snap_files = hostname + '_' + output_file
                            t = Thread(
                                target=self.connect,
                                args=(
                                    hostname,
                                    username,
                                    password,
                                    snap_files,
                                ))
                            t.start()
                            t.join()

        # login credentials are given in main config file
            else:
                hostname = k['devices']
                username = k['username']
                password = k['passwd']
                self.host_list.append(hostname)
                snap_files = hostname + '_' + output_file
                self.connect(hostname, username, password, snap_files)

        # if login credentials are given from command line
        else:
            hostname = self.args.hostname
            password = self.args.passwd
            username = self.args.login
            self.host_list.append(hostname)
            snap_files = hostname + '_' + output_file
            self.connect(hostname, username, password, snap_files)

    # function to connect to device
    def connect(self, hostname, username, password, snap_files):
        if self.args.snap is True:
            print "connecting to device %s ................" % hostname
            dev = Device(host=hostname, user=username, passwd=password)
            # print "\n going for snapshots"
            self.generate_rpc_reply(dev, snap_files)
        elif self.args.check is True or self.args.snapcheck is True or self.args.diff is True:
            # print "\n &&&&& going for comparision"
            testobj = self.compare_tests(hostname)
            if self.main_file.get("mail"):
                send_mail = Notification()
                send_mail.notify(self.main_file['mail'], hostname, testobj)

    # generate init folder
    def generate_init(self):
        if not os.path.isdir("snapshots"):
            os.mkdir("snapshots")
        dst_config_path = os.path.join(os.getcwd(), 'configs')
        # overwrite files if given option -o or --overwrite
        if not os.path.isdir(dst_config_path) or self.args.overwrite is True:
            distutils.dir_util.copy_tree(os.path.join(get_python_lib(), 'jnpr', 'jsnap', 'configs'),
                                         dst_config_path)
        dst_main_yml = os.path.join(dst_config_path, 'main.yml')
        if os.path.isfile(dst_main_yml) or self.args.overwrite is True:
            shutil.copy(dst_main_yml, os.getcwd())


def main():
    d = Jsnap()
    # make init folder
    if d.args.init is True:
        d.generate_init()
    else:
        d.get_hosts()

if __name__ == '__main__':
    main()
