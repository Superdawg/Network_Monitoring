#!/usr/bin/python
#
# Synopsis:
# ./check_script.py --addresses a.b.c.d[,...]
#                 [ --retry-interval int ]
#                 [ --retry-count int ]
#                 [ --exec-on-fail /path/to/script ]

from argparse import *

import logging
import os
import pingparsing
import subprocess

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
    def __init__(self, retryInterval=30, retryCount=2, addresses=None):
        self.log = Logger(name = "NetworkMonitor").getLogger()
        self.ping_parse = pingparsing.PingParsing()

        self.failedPing = []
        self.keepTesting = 1
        self.retryInterval = retryInterval
        self.retryCount = retryCount

        self.storeAddresses(addresses)

    def actOnFailure(self):
        """
        Now that we have determined that we have sufficiently failed, then we
        can move forward with performing the pre-determined action to resolve.
        """
        self.log.error("We FAILED BAD, we need to DO SOMETHING about it")

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
        if addresses is None:
            self.addressList = { '1.1.1.1': {},
                                 '4.2.2.2': {},
                                 '8.8.8.8': {} }
        else:
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
        failedRate = len(self.failedPing) / self.addressList
        if failedRate > 0.5:
            self.log.warn("Failed rate exceeds 50% Setting Retry in %s seconds" % self.retryInterval)
            time.sleep(self.retryInterval)

if __name__ == "__main__":
    addresses = [ '4.2.2.2',
                  '8.8.8.8',
                  '1.1.1.1' ]
    retryInterval = 30
    retryCount = 2

    NM = NetworkMonitor(retryInterval = retryInterval,
                        retryCount = retryCount,
                        addresses = addresses)
    NM.run()
