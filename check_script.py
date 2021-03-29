#!/usr/bin/python
#
# Synopsis:
# ./check_script.py --addresses a.b.c.d[,...]
#                 [ --retry-interval int ]
#                 [ --retry-count int ]
#                 [ --exec-on-fail /path/to/script ]

import argparse

import logging
import os
import pingparsing
import subprocess
import sys
import time

class Logger(object):
    def __init__(self, name, filename=None):
        self.loggerName = name

        if filename:
            self.filename = filename
        else:
            self.filename = None

    def getLogger(self):
        logger = logging.getLogger(self.loggerName)
        logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s-%(name)s-[%(process)d] %(message)s')
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        if self.filename:
            fhandler = logging.FileHandler(self.filename)
            fhandler.setFormatter(formatter)
            logger.addHandler(fhandler)
        return logger

class NetworkMonitor(object):
    def __init__(self, arguments):
        self.log = Logger(name = "NetworkMonitor").getLogger()
        self.ping_parse = pingparsing.PingParsing()
        self.parseArgs(arguments)

        self.failedPing = []
        self.keepTesting = 1

        self.storeAddresses(self.addresses)

    def parseArgs(self, arguments):
        parser = argparse.ArgumentParser(
                description=("Ping a number of hosts to determine whether "
                    "internet is functional and react accordingly"))
        parser.add_argument("--retry-interval",
                            dest="retry_interval",
                            default=30,
                            type=int,
                            help="The time to wait in between retries")
        parser.add_argument("--retry-count",
                            dest="retry_count",
                            default=2,
                            type=int,
                            help="The number of times to re-check before considering a failure")
        parser.add_argument("--exec-on-fail",
                            dest="fail_script",
                            default=None,
                            help="The command to invoke when there is a confirmed failure")
        parser.add_argument('--addresses',
                            action='store',
                            dest='addresses',
                            type=str,
                            nargs='+',
                            default=['1.1.1.1', '4.2.2.2', '8.8.8.8'],
                            help="The list of addresses to test (example: --addresses 1.1.1.1 4.2.2.2")
        args = parser.parse_args()

        #TODO: Add some error checking to make sure the arguments are real.
        self.retryInterval = args.retry_interval
        self.retryCount = args.retry_count
        self.failScript = args.fail_script
        self.addresses = args.addresses

    def actOnFailure(self):
        """
        Now that we have determined that we have sufficiently failed, then we
        can move forward with performing the pre-determined action to resolve.
        """
        self.log.error("We FAILED BAD, we need to DO SOMETHING about it")
        self.log.info("Running %s" % self.failScript)
        subprocess.call(self.failScript, shell=True)

        # Always exit with a failure since ... we failed?
        sys.exit(1)

    def run(self):
        # Continue to run ping tests until we determine that we're not
        # experiencing an outage
        loop = 0
        while self.keepTesting:
            for address in self.addressList:
                self.log.info("Checking Address '%s'" % address)
                ping_transmitter = pingparsing.PingTransmitter()
                ping_transmitter.destination = address
                ping_transmitter.count = 10
                ping_results = ping_transmitter.ping()

                self.addressList[address]['Stats'] = self.ping_parse.parse(ping_results).as_dict()

            self.processResults()

            if loop > self.retryCount:
                self.actOnFailure()

    def storeAddresses(self, addresses):
        # If the addresses weren't provided in the first place, then use these
        # addresses as the default set.
        self.addressList = {}
        for address in addresses:
            self.addressList[address] = {}

    def processResults(self):
        """
        Check each destination and determine whether we had more than 50%
        packet loss.  If so, then add that destination to a list to look at
        later.
        """
        for address in self.addressList:
            if self.addressList[address]['Stats']['packet_loss_rate'] > 0.5:
                self.failedPing.append(address)
        self.sleepIfFailed()

    def printStats(self):
            import pprint
            pprint.pprint(self.addressList)

    def sleepIfFailed(self):
        """
        Check how many "failed" destinations we have.  If we failed to reach
        more than half of them for more than half of their packets, then we
        should consider this a failure and sleep for the set period.
        """
        # We passed the test.  We're all good.
        if len(self.failedPing) == 0:
            self.keepTesting = 0
            return

        # Determine whether the number of failed destionations is more than 50%
        # of our total destinations.  If so, then sleep for the retry Interval
        # so that we can loop around when we finish.
        failedRate = len(self.failedPing) / len(self.addressList)
        if failedRate > 0.5:
            self.log.warning("Failed rate exceeds 50%% Setting Retry in %s seconds" % self.retryInterval)
            time.sleep(self.retryInterval)

if __name__ == "__main__":
    NM = NetworkMonitor(sys.argv)
    NM.run()
    sys.exit(0)
