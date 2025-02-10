# contindi
CONtrolling a Telescope using INDI - Simple Python client for INDI

**!!Work in progress!!**

This project is broken into several components:

- Basic control a personal telescope using INDI, using the `Connection` class.
  This allows for direct commands to be sent and recieved over python to an INDI server.
- A Scheduling server, which allows for jobs to be queued, and post processing to be
  run. This scheduling server uses the open source PocketBase as the primary software
  backend, enabling easy configuration of users and authentication.

This scheduling server does not need to be used at all if you just wish to control
your personal telescope.

Status:
- [x] - `Connection` - The basic communication via INDI is implemented and working.
- [ ] - `Scheduling Server` - This is starting to come together, but larger details
    still need to be sorted out.


## Example of direct connection to an INDI server

This is a pure python implementation of the INDI standard:
http://docs.indilib.org/protocol/INDI.pdf


``` python

    import contindi

    # This simple example has a device called "Telescope" and a device called "CCD"

    # Connect to an INDI server on the local computer
    cxn = contindi.Connection()

    # Query the current state of all devices connected to the INDI server
    cxn.state

    # Set the "Telescope" device to slew on coordinate set, and set the coordinates
    cxn.set_value("Telescope", "ON_COORD_SET", SLEW='On')
    cxn.set_value("Telescope", "EQUATORIAL_EOD_COORD", RA=15, DEC=10)

    # Abort!
    cxn.set_value("Telescope", "TELESCOPE_ABORT_MOTION", "on", block=False)

    # Command a 1 second exposure
    # This is not a blocking operation, so you will have to wait a second
    cxn.set_value("CCD", "CCD_EXPOSURE", 1.0, block=False)

    import time
    time.sleep(1.5)

    # Get the last frame recieved
    # In this case, if the format is a FITs file, it is automatically made into
    # an astropy FITS object. Otherwise the raw bytes are returned.
    cxn.state['CCD']['CCD1'].frame
```

### Technical Details

The above example uses multi-core processing to handle the connection to the INDI
server. A seperate thread is constantly reading from the server connection, and
the main thread can request a copy of the current state of the system. This means
images are received and stored in the second thread, and only on request copied to
the main thread.

