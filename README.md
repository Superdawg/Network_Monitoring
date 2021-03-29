# Network_Monitoring
This suite (well right now it's just a single script) is intended to be used on a Raspberry Pi controlling a power outlet that powers a modem.  It will confirm whether internet access is available and then act accordingly.

If the internet is sufficiently deemed to be "down" (for now, >50% packet loss to >50% of targets) then the script will invoke another script to manipulate the power outlet and effectively "reboot" the modem.

The default ping targets are `1.1.1.1`, `4.2.2.2`, and `8.8.8.8`.  This can be specified differently using the --addresses argument.
The default number of retries before considering things to be "down" is 2.
The default time between retries is set to 5 seconds (for development purposes), but should be set to something more like 15 minutes so that we don't end up rebooting the modem too frequently by being too sensitive.

The script is intended to be invoked via cron (or some other scheduler) every 30-60 minutes for maximum effect.

# Requirements
For now, this is primarily just a python3 script, but there is currently a dependency on the `pingparsing` library from pypi.  This lib is not available as a package in Fedora, so it must be installed via `pip3 install pingparsing`

# Example
To check 10.10.10.10 a maximum of **two** times with a **five** second sleep in between and then echo something to the console, this command would need to be used.

*Assume that 10.10.10.10 is an address that is not answering for this example*
```shell
./check_script.py --addresses 10.10.10.10 \
                  --retry-count 1 \
                  --retry-interval 5 \
                  --exec-on-fail "sh -c 'echo THIS WAS A COMPLETE AND UTTER FAILURE'"
```
