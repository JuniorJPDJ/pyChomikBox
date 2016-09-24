# pyChomikBox

Python 2.7 and 3.5 library for Chomikuj.pl filesharing service.

It uses official app's (ChomikBox) protocol to comunicate with Chomikuj servers.


Simple example of usage:

```
c = Chomik('login', 'password')
c.login()
print(c.list())
```

This code is logging at Chomikuj as `login` with password `password` and printing all files and folders of root folder.