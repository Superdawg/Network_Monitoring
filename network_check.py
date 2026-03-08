#!/usr/bin/python3
#
# Synopsis:
# ./network_check.py --addresses a.b.c.d[,...]
#                  [ --retry-interval int ]
#                  [ --retry-count int ]
#                  [ --exec-on-fail /path/to/script ]
#                  [ --email-recipients addr [addr ...] ]
#                  [ --email-relay host ]
#                  [ --notify-state-file /path/to/state ]
#                  [ --notify-cooldown int ]
#                  [ --reboot-cooldown int ]

import argparse
from email.message import EmailMessage
import json
import logging
import os
import pprint
import smtplib
import socket
import subprocess
import sys
import time

import pingparsing


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
        self.log = Logger(name="NetworkMonitor").getLogger()
        self.ping_parse = pingparsing.PingParsing()
        self.parseArgs()
        try:
            self.hostname = socket.getfqdn()
        except Exception:
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
        parser.add_argument("--notify-state-file",
                            dest="notify_state_file",
                            default="/var/run/network_check.state",
                            help=("Path to the file used to track outage state "
                                  "across invocations"))
        parser.add_argument("--notify-cooldown",
                            dest="notify_cooldown",
                            default=3600,
                            type=int,
                            help=("Minimum seconds between failure notification "
                                  "emails"))
        parser.add_argument("--reboot-cooldown",
                            dest="reboot_cooldown",
                            default=7200,
                            type=int,
                            help=("Minimum seconds between modem reboots"))
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
        # No validation is performed on fail_script by design — it accepts
        # arbitrary commands, as documented in README.md.

        self.retryInterval = args.retry_interval
        self.retryCount = args.retry_count
        self.failScript = args.fail_script
        self.addresses = args.addresses
        self.emails = args.emails
        self.relay = args.email_relay
        self.notifyStateFile = args.notify_state_file
        self.notifyCooldown = args.notify_cooldown
        self.rebootCooldown = args.reboot_cooldown

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
            except OSError:
                self.log.error("IP address (%s) is invalid" % ip)
                return False

        return True

    def actOnFailure(self):
        """
        Now that we have determined that we have sufficiently failed, then we
        can move forward with performing the pre-determined action to resolve.
        Reboots and notifications are each rate-limited by their respective
        cooldowns, with state persisted to disk across invocations.
        """
        self.printStats()
        now = time.time()
        state = self.loadState()

        # Rate-limit reboots: only reboot if no prior reboot has occurred
        # within the reboot cooldown window.
        if self.failScript is not None:
            last_reboot = state['last_reboot_time']
            if last_reboot is None or (now - last_reboot) >= self.rebootCooldown:
                self.log.info("Running %s" % self.failScript)
                subprocess.call(self.failScript, shell=True)
                state['last_reboot_time'] = now
                state['reboot_count'] += 1
            else:
                remaining = self.rebootCooldown - (now - last_reboot)
                self.log.warning("Reboot cooldown active. Next reboot "
                                 "eligible in %.0f seconds." % remaining)

        # Rate-limit failure notifications.
        last_notify = state['last_notify_time']
        if last_notify is None or (now - last_notify) >= self.notifyCooldown:
            self.notifyEmails()
            state['last_notify_time'] = now
        else:
            remaining = self.notifyCooldown - (now - last_notify)
            self.log.info("Notification cooldown active. Next notification "
                          "eligible in %.0f seconds." % remaining)

        self.saveState(state)
        sys.exit(1)

    def notifyEmails(self):
        """
        Send email notice if specified that we have acted on a failure.
        Notification frequency is controlled by the caller via notifyCooldown.
        """
        if self.emails is None:
            return

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
        message['Subject'] = ("[NETWORK FAILURE] %s - %s" %
                              (time.strftime("%Y%m%d-%H%M%S"), self.hostname))
        message['From'] = ("network_check@%s" % self.hostname)
        message['To'] = ', '.join(self.emails)

        # Now that we're finished assembling the message, let's send it along.
        smtp = smtplib.SMTP(self.relay)
        smtp.send_message(message)
        smtp.quit()

    def loadState(self):
        """
        Load outage state from the state file.  If the file does not exist,
        a fresh state is returned with first_failure_time set to now.  If the
        file is unreadable or malformed, a warning is logged and a fresh state
        is returned.
        """
        if os.path.exists(self.notifyStateFile):
            try:
                with open(self.notifyStateFile, 'r') as f:
                    return json.load(f)
            except (OSError, ValueError):
                self.log.warning("Could not read state file %s; starting "
                                 "fresh." % self.notifyStateFile)
        return {
            'first_failure_time': time.time(),
            'last_reboot_time': None,
            'reboot_count': 0,
            'last_notify_time': None,
        }

    def saveState(self, state):
        """
        Persist the outage state to disk.
        """
        try:
            with open(self.notifyStateFile, 'w') as f:
                json.dump(state, f)
        except OSError as e:
            self.log.error("Could not write state file %s: %s" %
                           (self.notifyStateFile, e))

    def clearState(self):
        """
        Remove the state file once internet connectivity has been restored.
        """
        if os.path.exists(self.notifyStateFile):
            try:
                os.remove(self.notifyStateFile)
            except OSError as e:
                self.log.error("Could not remove state file %s: %s" %
                               (self.notifyStateFile, e))

    def notifyRecovery(self, state):
        """
        Send an email indicating that internet connectivity has been restored,
        including the outage duration and the number of reboots performed.
        """
        if self.emails is None:
            return

        elapsed = time.time() - state['first_failure_time']
        hours, remainder = divmod(int(elapsed), 3600)
        minutes = remainder // 60

        message = EmailMessage()
        message.set_content(
            ("Internet connectivity has been restored on %s.\n\n"
             "Outage duration:            %d hour(s) %d minute(s)\n"
             "Modem reboots during outage: %d") %
            (self.hostname, hours, minutes, state['reboot_count']))
        message['Subject'] = ("[NETWORK RECOVERY] %s - %s" %
                              (time.strftime("%Y%m%d-%H%M%S"), self.hostname))
        message['From'] = ("network_check@%s" % self.hostname)
        message['To'] = ', '.join(self.emails)

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
            # Only act on a failure if we've hit the final loop AND we have
            # failures noted from the last round.
            if (loop > self.retryCount):
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

                    result = self.ping_parse.parse(ping_results)
                    self.addressList[address]['Stats'] = result.as_dict()

                loop += 1

                # Account for the results from each of the ping tests.
                self.processResults()

                # Look at the results and sleep if there is any amount of
                # failure.  Otherwise just return for the next loop.
                self.sleepIfFailed()

        # If a state file exists, internet has recovered from a prior outage.
        # Send a recovery notification and clean up the state file.
        if os.path.exists(self.notifyStateFile):
            state = self.loadState()
            self.log.info("Internet connectivity restored after outage.")
            self.notifyRecovery(state)
            self.clearState()

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
            self.log.info("No failures to handle, moving along.")
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
            self.log.info("Failed host rate (%s) < 50%%.  Moving along." % (failedRate))
            # Clear our Keep Testing flag since we didn't notice more than 50%
            # of the hosts as being unreachable.
            self.keepTesting = 0


if __name__ == "__main__":
    NM = NetworkMonitor()
    NM.run()
    sys.exit(0)
