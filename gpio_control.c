#include <err.h>
#include <getopt.h>
#include <stdio.h>
#include <stdlib.h>
#include <pigpio.h>

int main(int argc, char *argv[])
{
        if (gpioInitialise() < 0)
        {
                fprintf(stderr, "pigpio initialization failed\n");
                return 1;
        }

        int opt;
        int delay = 300;
        int pin = 18;
        while ((opt = getopt(argc, argv, "d:p:")) != -1) {
                switch (opt) {
                case 'd':
                        delay = atoi(optarg);
                        break;
                case 'p':
                        pin = atoi(optarg);
                        break;
                default:
                        fprintf(stderr, "Usage: %s [-d NUM] [-p NUM]\n", argv[0]);
                        fprintf(stderr, "\t-d\t Time (in seconds) to keep the pin activated\n");
                        fprintf(stderr, "\t-p\t The pin to activate (MUST BE pins x,y,z,...)\n");
                        exit(0);
                }
        }
        printf("Given delay %d\n", delay);
        printf("Given pin %d\n", pin);

        // Turn the supplied pin on.
        fprintf(stdout, "Turning pin %d on\n", pin);
        //gpioWrite(pin, 1);

        // Sleep for the requested time.
        fprintf(stdout, "Sleeping for %d seconds\n", delay);
        time_sleep(delay);

        // Turn the supplied pin off.
        fprintf(stdout, "Turning pin %d off\n", pin);
        //gpioWrite(pin, 0);

        return 0;
}
