#!/usr/bin/python3
"""
Monitor internet connectivity by pinging a set of hosts and cycling a
GPIO-controlled power outlet to reboot the modem on confirmed failure.

Outage state is persisted across invocations so that reboots and failure
notifications are rate-limited independently of how frequently the script
is scheduled to run.  A recovery email is sent when connectivity returns.

Synopsis:
  ./network_check.py --addresses a.b.c.d[,...]
                   [ --retry-interval int ]
                   [ --retry-count int ]
                   [ --exec-on-fail /path/to/script ]
                   [ --email-recipients addr [addr ...] ]
                   [ --email-relay host ]
                   [ --notify-state-file /path/to/state ]
                   [ --notify-cooldown int ]
                   [ --reboot-cooldown int ]
                   [ --traceroute-address a.b.c.d ]
                   [ --reboot-hop-threshold int ]
"""

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


class Logger:
    """Thin wrapper around the standard logging module providing a pre-configured
    logger with a consistent format, optionally writing to a log file."""

    def __init__(self, name, filename=None):
        self.logger_name = name

        if filename:
            self.filename = filename
        else:
            self.filename = None

    def get_logger(self):
        """Build and return the configured logger instance."""
        logger = logging.getLogger(self.logger_name)
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


class NetworkMonitor:
    """Monitors internet connectivity by pinging known hosts and acting on
    confirmed failures according to configurable retry and cooldown policies."""

    def __init__(self):
        self.log = Logger(name="NetworkMonitor").get_logger()
        self.ping_parse = pingparsing.PingParsing()
        self.parse_args()
        try:
            self.hostname = socket.getfqdn()
        except OSError:
            self.log.error("Unable to detect proper hostname")
            sys.exit(1)

        self.keep_testing = 1
        self.failed_ping = []
        self.num_pings = 10

        self.store_addresses(self.addresses)

    def parse_args(self):
        """Parse command-line arguments and store them as instance attributes."""
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
                            help="The SMTP/MTA to use for sending the email")
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
                            help="Minimum seconds between modem reboots")
        parser.add_argument("--traceroute-address",
                            dest="traceroute_address",
                            default=None,
                            help=("IPv4 address to traceroute to when pings fail, used to "
                                  "determine whether the failure is close enough to the modem "
                                  "to warrant a reboot.  If unset, a reboot is always attempted "
                                  "on confirmed failure (original behaviour)."))
        parser.add_argument("--reboot-hop-threshold",
                            dest="reboot_hop_threshold",
                            default=2,
                            type=int,
                            help=("Only reboot the modem if the first fully-unresponsive "
                                  "traceroute hop is at or below this value.  A value of 2 "
                                  "means the failure must be at the ISP's first router to "
                                  "justify a reboot. (default: 2)"))
        args = parser.parse_args()

        fail = 0
        if ((args.retry_interval < 0) or (args.retry_count < 0)):
            self.log.error(f"Invalid retry interval ({args.retry_interval}) or "
                           f"retry count ({args.retry_count}) requested.")
            fail = 1
        if not self.verify_address_format(args.addresses):
            self.log.error(f"Invalid IP address specified in list ({', '.join(args.addresses)})")
            fail = 1
        if args.traceroute_address is not None:
            if not self.verify_address_format([args.traceroute_address]):
                self.log.error(f"Invalid traceroute address: {args.traceroute_address}")
                fail = 1
        if args.reboot_hop_threshold < 1:
            self.log.error(f"Invalid reboot hop threshold ({args.reboot_hop_threshold}); "
                           f"must be >= 1.")
            fail = 1
        # No validation is performed on fail_script by design — it accepts
        # arbitrary commands, as documented in README.md.

        self.retry_interval = args.retry_interval
        self.retry_count = args.retry_count
        self.fail_script = args.fail_script
        self.addresses = args.addresses
        self.emails = args.emails
        self.relay = args.email_relay
        self.notify_state_file = args.notify_state_file
        self.notify_cooldown = args.notify_cooldown
        self.reboot_cooldown = args.reboot_cooldown
        self.traceroute_address = args.traceroute_address
        self.reboot_hop_threshold = args.reboot_hop_threshold

        if fail:
            parser.print_usage()
            sys.exit(1)

    def verify_address_format(self, addresses):
        """
        Loop through the provided IP addresses and make sure they are all valid
        IP addresses
        """
        for ip in addresses:
            try:
                socket.inet_aton(ip)
            except OSError:
                self.log.error(f"IP address ({ip}) is invalid")
                return False

        return True

    def act_on_failure(self):
        """
        Now that we have determined that we have sufficiently failed, then we
        can move forward with performing the pre-determined action to resolve.
        Reboots and notifications are each rate-limited by their respective
        cooldowns, with state persisted to disk across invocations.
        """
        self.print_stats()
        now = time.time()
        state = self.load_state()

        # Rate-limit reboots.  On the first failure, start the cooldown clock
        # without rebooting so that a single blip never cycles the modem.
        # Subsequent failures reboot once the cooldown window has elapsed.
        #
        # When a traceroute address is configured, first check which hop is the
        # first to go silent.  If the failure is beyond the reboot threshold it
        # is upstream of the modem and a reboot won't help.  If the traceroute
        # is inconclusive (error, timeout, or no silent hop found), fall back to
        # the original behaviour and attempt a reboot.
        if self.fail_script is not None:
            first_silent_hop = self.check_failure_hop()
            if first_silent_hop is not None and first_silent_hop > self.reboot_hop_threshold:
                self.log.warning(
                    f"First unresponsive traceroute hop ({first_silent_hop}) exceeds "
                    f"reboot threshold ({self.reboot_hop_threshold}). "
                    f"Failure is upstream of the modem; skipping reboot.")
            else:
                if first_silent_hop is None and self.traceroute_address is not None:
                    self.log.warning("Traceroute inconclusive; defaulting to reboot behaviour.")
                elif first_silent_hop is not None:
                    self.log.warning(
                        f"First unresponsive traceroute hop ({first_silent_hop}) is within "
                        f"reboot threshold ({self.reboot_hop_threshold}). Proceeding with reboot.")
                last_reboot = state['last_reboot_time']
                if last_reboot is None:
                    self.log.warning(f"First failure detected. Reboot will trigger "
                                     f"after cooldown ({self.reboot_cooldown:.0f} seconds).")
                    state['last_reboot_time'] = now
                elif (now - last_reboot) >= self.reboot_cooldown:
                    self.log.info(f"Running {self.fail_script}")
                    subprocess.call(self.fail_script, shell=True)
                    state['last_reboot_time'] = now
                    state['reboot_count'] += 1
                else:
                    remaining = self.reboot_cooldown - (now - last_reboot)
                    self.log.warning(f"Reboot cooldown active. Next reboot "
                                     f"eligible in {remaining:.0f} seconds.")

        # Rate-limit failure notifications.
        last_notify = state['last_notify_time']
        if last_notify is None or (now - last_notify) >= self.notify_cooldown:
            self.notify_emails()
            state['last_notify_time'] = now
        else:
            remaining = self.notify_cooldown - (now - last_notify)
            self.log.info(f"Notification cooldown active. Next notification "
                          f"eligible in {remaining:.0f} seconds.")

        self.save_state(state)
        sys.exit(1)

    def notify_emails(self):
        """
        Send email notice if specified that we have acted on a failure.
        Notification frequency is controlled by the caller via notifyCooldown.
        """
        if self.emails is None:
            return

        message = EmailMessage()
        message.set_content("The Network Monitoring Script has taken action "
                            "to reboot the modem.  Please review the "
                            "statistics to verify the results."
                            "\n\n"
                            f"Stats: {pprint.pformat(self.address_list)}")

        # Keeping a timestamp in the subject is important since this message
        # may be getting delivered significantly later than the actual action.
        # If this event triggers, that means internet is considered to be down.
        # This message won't be delivered until internet connectivity has been
        # restored.
        message['Subject'] = f"[NETWORK FAILURE] {time.strftime('%Y%m%d-%H%M%S')} - {self.hostname}"
        message['From'] = f"network_check@{self.hostname}"
        message['To'] = ', '.join(self.emails)

        # Now that we're finished assembling the message, let's send it along.
        smtp = smtplib.SMTP(self.relay)
        smtp.send_message(message)
        smtp.quit()

    def load_state(self):
        """
        Load outage state from the state file.  If the file does not exist,
        a fresh state is returned with first_failure_time set to now.  If the
        file is unreadable or malformed, a warning is logged and a fresh state
        is returned.
        """
        if os.path.exists(self.notify_state_file):
            try:
                with open(self.notify_state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (OSError, ValueError):
                self.log.warning(f"Could not read state file {self.notify_state_file}; "
                                 f"starting fresh.")
        return {
            'first_failure_time': time.time(),
            'last_reboot_time': None,
            'reboot_count': 0,
            'last_notify_time': None,
        }

    def save_state(self, state):
        """
        Persist the outage state to disk.
        """
        try:
            with open(self.notify_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f)
        except OSError as e:
            self.log.error(f"Could not write state file {self.notify_state_file}: {e}")

    def clear_state(self):
        """
        Remove the state file once internet connectivity has been restored.
        """
        if os.path.exists(self.notify_state_file):
            try:
                os.remove(self.notify_state_file)
            except OSError as e:
                self.log.error(f"Could not remove state file {self.notify_state_file}: {e}")

    def check_failure_hop(self):
        """
        Run traceroute to the configured traceroute address and return the first
        hop number where all probes are unresponsive.  Returns None if no
        traceroute address is configured, the command fails, times out, or no
        fully-silent hop is found within the hop limit (all inconclusive cases).
        """
        if self.traceroute_address is None:
            return None
        try:
            result = subprocess.run(
                ['traceroute', '-n', '-m', '10', self.traceroute_address],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,  # non-zero exit is expected when destination is unreachable
            )
            return self._parse_first_silent_hop(result.stdout)
        except (OSError, subprocess.TimeoutExpired) as e:
            self.log.warning(f"traceroute to {self.traceroute_address} failed: {e}; "
                             f"falling back to default reboot behaviour.")
            return None

    def _parse_first_silent_hop(self, output):
        """
        Parse traceroute stdout and return the hop number of the first hop where
        every probe timed out (i.e. all tokens after the hop number are '*').
        Returns None if no fully-silent hop is found.
        """
        for line in output.splitlines():
            parts = line.split()
            if not parts or not parts[0].isdigit():
                continue
            hop_num = int(parts[0])
            responses = parts[1:]
            if responses and all(r == '*' for r in responses):
                return hop_num
        return None

    def notify_recovery(self, state):
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
            f"Internet connectivity has been restored on {self.hostname}.\n\n"
            f"Outage duration:            {hours} hour(s) {minutes} minute(s)\n"
            f"Modem reboots during outage: {state['reboot_count']}")
        timestamp = time.strftime('%Y%m%d-%H%M%S')
        message['Subject'] = f"[NETWORK RECOVERY] {timestamp} - {self.hostname}"
        message['From'] = f"network_check@{self.hostname}"
        message['To'] = ', '.join(self.emails)

        smtp = smtplib.SMTP(self.relay)
        smtp.send_message(message)
        smtp.quit()

    def run(self):
        """Run ping tests in a loop until connectivity is confirmed or the retry
        limit is exceeded, then act on failure or send a recovery notification."""
        # Continue to run ping tests until we determine that we're not
        # experiencing an outage
        loop = 0
        while self.keep_testing:
            # (re)set the faildPing list on each loop since we don't want to
            # keep adding the same hosts every time if they are down.
            self.failed_ping = []

            self.log.info(f"Loop: {loop}, retry count max: {self.retry_count}")
            # Only act on a failure if we've hit the final loop AND we have
            # failures noted from the last round.
            if loop > self.retry_count:
                self.log.warning(("Maximum Retry count exceeded.  Performing "
                                 "action."))
                self.act_on_failure()
                self.keep_testing = 0
            else:
                for address, data in self.address_list.items():
                    self.log.info(f"Checking Address '{address}'")
                    ping_transmitter = pingparsing.PingTransmitter()
                    ping_transmitter.destination = address
                    ping_transmitter.count = self.num_pings

                    ping_results = ping_transmitter.ping()

                    result = self.ping_parse.parse(ping_results)
                    data['Stats'] = result.as_dict()

                loop += 1

                # Account for the results from each of the ping tests.
                self.process_results()

                # Look at the results and sleep if there is any amount of
                # failure.  Otherwise just return for the next loop.
                self.sleep_if_failed()

        # If a state file exists, internet has recovered from a prior outage.
        # Send a recovery notification and clean up the state file.
        if os.path.exists(self.notify_state_file):
            state = self.load_state()
            self.log.info("Internet connectivity restored after outage.")
            self.notify_recovery(state)
            self.clear_state()

    def store_addresses(self, addresses):
        """
        Take the addresses from their list format and place them in the
        dictionary that will eventually hold the statistics.
        """
        self.address_list = {}
        for address in addresses:
            self.address_list[address] = {}

    def process_results(self):
        """
        Check each destination and determine whether we had more than 50%
        packet loss.  If so, then add that destination to a list to look at
        later.
        """
        for address, data in self.address_list.items():
            self.log.info(
                f"{address} - Sent/Received: "
                f"{data['Stats']['packet_transmit']}/"
                f"{data['Stats']['packet_receive']}")

            # If any particular host has 50% or more packet loss, then they
            # should be added to the list of failed pings.
            if ((data['Stats']['packet_loss_rate'] is None) or
                    (data['Stats']['packet_loss_rate'] >= 50)):
                self.log.warning(
                    f"Packet loss for {address}: "
                    f"{data['Stats']['packet_loss_rate']}")
                self.failed_ping.append(address)

    def print_stats(self):
        """Print the full address statistics dictionary to stdout."""
        pprint.pprint(self.address_list)

    def sleep_if_failed(self):
        """
        Check how many "failed" destinations we have.  If we failed to reach
        more than half of them for more than half of their packets, then we
        should consider this a failure and sleep for the set period.
        """
        # If we didn't have any failures added to the list, then we're done.
        if len(self.failed_ping) == 0:
            self.keep_testing = 0
            self.log.info("No failures to handle, moving along.")
            return

        # Determine whether the number of failed destionations is more than 50%
        # of our total destinations.  If so, then sleep for the retry Interval
        # so that we can loop around when we finish.
        failed_rate = len(self.failed_ping) / len(self.address_list)
        if failed_rate >= 0.5:
            self.log.warning(f"Failed host rate ({failed_rate}) matches >=50%. "
                             f"Retrying in {self.retry_interval} seconds")
            time.sleep(self.retry_interval)
        else:
            self.log.info(f"Failed host rate ({failed_rate}) < 50%.  Moving along.")
            # Clear our Keep Testing flag since we didn't notice more than 50%
            # of the hosts as being unreachable.
            self.keep_testing = 0


if __name__ == "__main__":
    NM = NetworkMonitor()
    NM.run()
    sys.exit(0)
