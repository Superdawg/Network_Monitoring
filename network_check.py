#!/usr/bin/python3
#
# Synopsis:
# ./check_script.py --addresses a.b.c.d[,...]
#                 [ --retry-interval int ]
#                 [ --retry-count int ]
#                 [ --exec-on-fail /path/to/script ]

import argparse
from email.message import EmailMessage
import logging
import os
import pingparsing
import pprint
import smtplib
import socket
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
    def __init__(self):
        self.log = Logger(name = "NetworkMonitor").getLogger()
        self.ping_parse = pingparsing.PingParsing()
        self.parseArgs()
        try:
            self.hostname = socket.getfqdn()
        except Exception as error:
            self.log.error("Unable to detect proper hostname")
            sys.exit(1)

        self.keepTesting = 1

        self.numPings = 10

        self.storeAddresses(self.addresses)

    def parseArgs(self):
        parser = argparse.ArgumentParser(
                description=("Ping a number of hosts to determine whether "
                             "internet is functional and react accordingly"))
        parser.add_argument('--addresses',
                            action='store',
                            dest='addresses',
                            type=str,
                            nargs='+',
                            default=['1.1.1.1', '4.2.2.2', '8.8.8.8'],
                            help="The list of addresses to test")
        parser.add_argument("--exec-on-fail",
                            dest="fail_script",
                            default=None,
                            help=("The command to invoke when there is a "
                                  "confirmed failure"))
        parser.add_argument('--email-recipients',
                            action='store',
                            dest='emails',
                            type=str,
                            nargs='+',
                            default=None,
                            help=("The list of email addresses to notify when "
                                  "there is a confirmed failure"))
        parser.add_argument('--email-relay',
                            action='store',
                            dest='email_relay',
                            type=str,
                            default='localhost',
                            help=("The SMTP/MTA to use for sending the email"))
        parser.add_argument("--retry-count",
                            dest="retry_count",
                            default=2,
                            type=int,
                            help=("The number of times to re-check before "
                                  "considering a failure.  Must be a positive "
                                  "integer."))
        parser.add_argument("--retry-interval",
                            dest="retry_interval",
                            default=30,
                            type=int,
                            help=("The time to wait in between retries.  Must "
                                  "be a positive integer."))
        args = parser.parse_args()

        fail = 0
        if ((args.retry_interval < 0) or (args.retry_count < 0)):
            self.log.error(("Invalid retry interval (%i) or retry count(%i) "
                            "requested.") %
                           (args.retry_interval, args.retry_count))
            fail = 1
        if not self.verifyAddressFormat(args.addresses):
            self.log.error("Invalid IP address specified in list (%s)" %
                           ', '.join(args.addresses))
            fail = 1
        #XXX: There is no validation against the fail_script since it can be
        #     anything from another script, to a full on command (like what is
        #     specified in the README.md for this project)

        self.retryInterval = args.retry_interval
        self.retryCount = args.retry_count
        self.failScript = args.fail_script
        self.addresses = args.addresses
        self.emails = args.emails
        self.relay = args.email_relay

        if fail:
            parser.print_usage()
            sys.exit(1)

    def verifyAddressFormat(self, addresses):
        """
        Loop through the provided IP addresses and make sure they are all valid
        IP addresses
        """
        for ip in addresses:
            try:
                socket.inet_aton(ip)
            #XXX: Generic exception catch.  Maybe it'll fail on something else,
            #     but we'll be trusting for now.
            except Exception:
                self.log.error("IP address (%s) is invalid" % ip)
                return False

        return True

    def actOnFailure(self):
        """
        Now that we have determined that we have sufficiently failed, then we
        can move forward with performing the pre-determined action to resolve.
        """
        self.printStats()

        if self.failScript is not None:
            self.log.info("Running %s" % self.failScript)
            subprocess.call(self.failScript, shell=True)

        # Send out emails to indicate that we acted.
        self.notifyEmails()

        # Always exit with a failure since ... we failed?
        sys.exit(1)

    def notifyEmails(self):
        """
        Send email notice if specified that we have acted on a failure
        """
        message = EmailMessage()
        message.set_content(("The Network Monitoring Script has taken action "
                             "to reboot the modem.  Please review the "
                             "statistics to verify the results."
                             "\n\n"
                             "Stats: %s" % pprint.pformat(self.addressList)))

        # Keeping a timestamp in the subject is important since this message
        # may be getting delivered significantly later than the actual action.
        # If this event triggers, that means internet is considered to be down.
        # This message won't be delivered until internet connectivity has been
        # restored.
        #XXX: If the connection is down for a long time, then there could be a
        #     large number of these messages queued up.  This should probably
        #     be taken into account somehow.
        message['Subject'] = ("[NETWORK FAILURE] %s - %s" %
            (time.strftime("%Y%m%d-%H%M%S"), self.hostname))
        message['From'] = ("network_check@%s" % self.hostname)
        message['To'] = ', '.join(self.emails)

        # Now that we're finished assembilng the message, let's send it along.
        smtp = smtplib.SMTP(self.relay)
        smtp.send_message(message)
        smtp.quit()

    def run(self):
        # Continue to run ping tests until we determine that we're not
        # experiencing an outage
        loop = 0
        while self.keepTesting:
            # (re)set the faildPing list on each loop since we don't want to
            # keep adding the same hosts every time if they are down.
            self.failedPing = []

            self.log.info("Loop: %i, retry count max: %i" % (loop,
                                                             self.retryCount))
            if loop > self.retryCount:
                self.log.warning(("Maximum Retry count exceeded.  Performing "
                                 "action."))
                self.actOnFailure()
                self.keepTesting = 0
            else:
                for address in self.addressList:
                    self.log.info("Checking Address '%s'" % address)
                    ping_transmitter = pingparsing.PingTransmitter()
                    ping_transmitter.destination = address
                    ping_transmitter.count = self.numPings

                    ping_results = ping_transmitter.ping()

                    self.addressList[address]['Stats'] = self.ping_parse.parse(ping_results).as_dict()

                loop += 1

                # Account for the results from each of the ping tests.
                self.processResults()

                # I don't like this...  But for now... After we've incremented
                # the loop counter, if we're at the limit, don't bother
                # sleeping.
                if loop <= self.retryCount:
                    self.sleepIfFailed()


    def storeAddresses(self, addresses):
        """
        Take the addresses from their list format and place them in the
        dictionary that will eventually hold the statistics.
        """
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
            self.log.info("%s - Sent/Received: %s/%s" %
                         (address,
                          self.addressList[address]['Stats']['packet_transmit'],
                          self.addressList[address]['Stats']['packet_receive']))

            # If any particular host has 50% or more packet loss, then they
            # should be added to the list of failed pings.
            if ((self.addressList[address]['Stats']['packet_loss_rate'] is None) or
                (self.addressList[address]['Stats']['packet_loss_rate'] >= 50)):
                self.log.warning("Packet loss for %s: %s" %
                                 (address,
                                  self.addressList[address]['Stats']['packet_loss_rate']))
                self.failedPing.append(address)

    def printStats(self):
            pprint.pprint(self.addressList)

    def sleepIfFailed(self):
        """
        Check how many "failed" destinations we have.  If we failed to reach
        more than half of them for more than half of their packets, then we
        should consider this a failure and sleep for the set period.
        """
        # If we didn't have any failures added to the list, then we're done.
        if len(self.failedPing) == 0:
            self.keepTesting = 0
            return

        # Determine whether the number of failed destionations is more than 50%
        # of our total destinations.  If so, then sleep for the retry Interval
        # so that we can loop around when we finish.
        failedRate = len(self.failedPing) / len(self.addressList)
        if failedRate >= 0.5:
            self.log.warning("Failed host rate (%s) matches >=50%%. Retrying in %s seconds" %
                            (failedRate, self.retryInterval))
            time.sleep(self.retryInterval)
        else:
            # Clear our Keep Testing flag since we didn't notice more than 50%
            # of the hosts as being unreachable.
            self.keepTesting = 0

if __name__ == "__main__":
    NM = NetworkMonitor()
    NM.run()
    sys.exit(0)
