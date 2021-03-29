PROGS = gpio_control

$(PROGS):
	@echo "Building $@"
	$(CC)  $@.c -o $@ -lpigpio -lrt -lpthread

all: $(PROGS)

clean:
	rm -v $(PROGS)
