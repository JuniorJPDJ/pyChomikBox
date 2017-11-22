pyChomikBox
===========

Python 2.7 and 3.5 (and wasn't tested at lower versions) library for Chomikuj.pl file sharing service.
It uses official app's (ChomikBox) protocol to comunicate with Chomikuj servers.


Installation
------------

Just use pip, as you would with all python packages

.. code-block:: bash

    $ pip install pyChomikBox


Examples
--------

A simple example of usage

.. code-block:: python

    >>> from ChomikBox import Chomik
    >>> c = Chomik('username', 'password')
    >>> c.login()
    >>> c
    <ChomikBox.Chomik: username>
    >>> print(c.list())
    [<ChomikBox.ChomikFolder: "/prywatne/" (username)>, <ChomikBox.ChomikFolder: "/zachomikowane/" (username)>]

This code is logging at Chomikuj as `username` with password `password` and printing all files and folders of root folder.

You can find more examples in `examples` directory.
