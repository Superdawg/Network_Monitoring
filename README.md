# Network Monitoring and Recovery
This suite is intended to be used on a Raspberry Pi controlling a power outlet that powers a modem.  It will confirm whether internet access is available and then act accordingly.

The python script should be invoked via cron (or some other scheduler) every 30-60 minutes to reduce the amount of extraneous reboots in the event that a reboot doesn't fix the problem.  Since the internet connection could be down for other reasons, it should be taken into consideration that this suite will reboot the modem repeatedly without regard.  If a device is repeatedly cycled, it could cause unnecessary wear and tear, so it's best to reasonably limit the number of cycles (but it's up to the owner to decide!).

If the internet is sufficiently deemed to be "down" (for now, >50% packet loss to >50% of targets; maybe this can be configurable later) then the `check_script.py`script will invoke gpio_control (or something else that you want) to manipulate the power outlet and effectively "reboot" the modem.

The default ping targets are `1.1.1.1`, `4.2.2.2`, and `8.8.8.8`.  This can be specified differently using the **--addresses** argument.
The default number of retries before considering things to be **down** is *2*.
The default time between retries is set to *5* seconds (**for development purposes**), but should be set to something more like **15 minutes** so that we don't end up rebooting the modem too frequently by being too sensitive.

# Requirements
For now, this is primarily just a python3 script, but there is currently a dependency on the `pingparsing` library from pypi.  This lib is not available as a package in Fedora, so it must be installed via `pip3 install pingparsing`

# Example
To check 10.10.10.10 a maximum of **two** times with a **five** second sleep in between and then trigger a signal via GPIO pin 23 for 15 seconds, this command would need to be used.

*Assume that 10.10.10.10 is an address that is not answering for this example*
```shell
./check_script.py --addresses 10.10.10.10 \
                  --retry-count 1 \
                  --retry-interval 5 \
                  --exec-on-fail "/home/pi/Network_Monitoring/gpio_control -d 15 -p 23"
```

# Getting up and running on Raspbian Buster
As of 2021-03-29, this is the procedure to get a freshly installed version of Raspbian Buster running.
```
sudo apt-get install -y git libpigpio-dev python3-pip
pip3 install pingparsing
git clone https://github.com/Superdawg/Network_Monitoring.git
cd Network_Monitoring
make
python3 ./check_script.py --retry-interval 5 --retry-count 1 --addresses 10.10.10.10 --exec-on-fail "sudo /home/pi/Network_Monitoring//gpio_control -d 15 -p 23"
```

If you then place this into a cron job (or some other scheduler), it will be able to automatially cycle the power on the power strip when there is an outage detected.

# Equipment used
~$52 USD - [Raspberry Pi 3b+](https://www.amazon.com/CanaKit-Raspberry-Power-Supply-Listed/dp/B07BC6WH7V)

~$30 USD - [IOT Relay Power Strip](https://www.adafruit.com/product/2935)

~$8 USD - [32GB Samsung EVO microSD card](https://www.amazon.com/Samsung-MicroSDHC-Adapter-MB-ME32GA-AM/dp/B06XWN9Q99)
