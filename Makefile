PROGS = gpio_control

$(PROGS):
	@echo "Building $@"
	$(CC)  $@.c -o $@ -lpigpio -lrt -lpthread

all: $(PROGS)

install: $(PROGS)
	@echo Installing gpio_control to /usr/sbin
	install -m 4755 -o root -g root gpio_control /usr/sbin/gpio_control
	@echo Installing network_monitor to /usr/bin
	install -m 0755 -o nobody -g nogroup network_check.py /usr/bin/network_check
	@echo Installing systemd components
	install -m 0644 -o root -g root network_check.timer /usr/lib/systemd/system/network_check.timer
	install -m 0644 -o root -g root network_check.service /usr/lib/systemd/system/network_check.service
	@echo Enabling and starting the network_check timer.
	systemctl enable power_check.timer
	systemctl start power_check.timer

clean:
	rm -v $(PROGS)
