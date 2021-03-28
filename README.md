# Network_Monitoring
This suite (well right now it's just a single script) is intended to be used on a Raspberry Pi controlling a power outlet that powers a modem.  It will confirm whether internet access is available and then act accordingly.

If the internet is sufficiently deemed to be "down" (for now, >50% packet loss to >50% of targets) then the script will invoke another script to manipulate the power outlet and effectively "reboot" the modem.

The default ping targets are `1.1.1.1`, `4.2.2.2`, and `8.8.8.8`.  This will be configurable later on.
The default number of retries before considering things to be "down" is 2.
The default time between retries is set to 30 seconds (for development purposes), but should be set to something more like 15 minutes so that we don't end up rebooting the modem too frequently by being too sensitive.

The script is intended to be invoked via cron (or some other scheduler) every 30-60 minutes for maximum effect.
