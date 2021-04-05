#include <getopt.h>
#include <pigpio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Currently the acceptable pins to use for general purpoase GPIO signals are
// listed below.
int GPIO_SIZE = 10;
int gpio[10] = { 5, 6, 16, 17, 22, 23, 24, 25, 26, 27 };

/**
 * Assemble the list of acceptable pins in a comma-formatted (not separated)
 * list.
 **/
const char *print_csv_pins(char* result)
{
        for (int i = 0; i < GPIO_SIZE; i++)
        {
                char ftext[255];
                if ((i + 1) == GPIO_SIZE)
                {
                        int appended = snprintf(ftext, 255, "%i", gpio[i]);
                } else {
                        int appended = snprintf(ftext, 255, "%i, ", gpio[i]);
                }
                strcat(result, ftext);
        }
}

/**
 * Print the usage for the program...
 **/
void printUsage(char arg[255])
{
        char csv_pins[1024];
        print_csv_pins(csv_pins);
        fprintf(stderr, "Usage: %s [-d NUM] [-p NUM]\n", arg);
        fprintf(stderr, "\t-d\t Time (in seconds) to keep the pin activated\n");
        fprintf(stderr, "\t-p\t The pin to activate (MUST BE one of %s)\n", csv_pins);
        exit(1);
}

/**
 * Verify that the pin that was requested is appropriate for this purpose.  An
 * 'acceptable' pin is labelled generically as GPIO<num> pin from the raspberry
 * pi reference.
 *
 * Example reference:
 * https://www.raspberrypi.org/documentation/usage/gpio/images/GPIO-Pinout-Diagram-2.png
 **/
int validatePin(int pin, char arg[255])
{
        // Check the specified pin against the list and return if it's been
        // found.
        for (int i = 0; i < sizeof(gpio); i++)
        {
                if (gpio[i] == pin)
                {
                        return pin;
                }
        }

        char csv_pins[1024];
        print_csv_pins(csv_pins);
        fprintf(stderr, "Pin %i is not acceptable.  Must be one of %s\n", pin, csv_pins);
        exit(1);

        return pin;
}

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
                        pin = validatePin(atoi(optarg), argv[0]);
                        break;
                default:
                        printUsage(argv[0]);
                }
        }
        printf("Given delay %d\n", delay);
        printf("Given pin %d\n", pin);

        // Turn the supplied pin on.
        fprintf(stdout, "Turning pin %d on\n", pin);
        gpioWrite(pin, 1);

        // Sleep for the requested time.
        fprintf(stdout, "Sleeping for %d seconds\n", delay);
        time_sleep(delay);

        // Turn the supplied pin off.
        fprintf(stdout, "Turning pin %d off\n", pin);
        gpioWrite(pin, 0);

        return 0;
}
