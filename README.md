# SlipCover - **Alpha Release**

>
> This software is not complete and definitely not ready for any real-world deployment yet. I'm only exposing it as a curiosity for CouchDB developers or anyone interested in lightweight application server architecture.

A lightweight application server for [CouchDB](https://github.com/apache/couchdb).

SlipCover is based on the [Twisted](http://twistedmatrix.com/) networking engine. It is designed to sit in front of a CouchDB server and provide functionality that is difficult or impossible to provide through native CouchDB requests.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes. See deployment for notes on how to deploy the project on a live system.

### Prerequisites

To run SlipCover you will first need to [install CouchDB](https://couchdb.apache.org/). Then you will need to install the Twisted framework:

```
pip install twisted
```

### Installing

To install SlipCover you will need to create a `slipcover` database in the local CouchDB server. Create a `config` document that will be loaded on SlipCover startup:

```
{
  "_id": "config",
  "server_config": {
    "http_port": 8080
  },
  "default_db": "maindb",
  "handlers": [
    "slipcover.sessions",
    "slipcover.cors"
  ]
}
```

To support CouchDB authentication, you must set the `COUCHUSER` and `COUCHPASS` environment variables with a valid CouchDB login.

```
export COUCHUSER=myuser
export COUCHPASS=***secret***
```

To run the server, execute the `slipcover` package using a Python 3 interpreter:

```
python3 slipcover/
```

## Authors

* **Scott Means** - *Initial work* - [GitHub](https://github.com/smeans)

See also the list of [contributors](https://github.com/smeans/slipcover/contributors) who participated in this project.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

## Acknowledgments

* [CouchDB](https://github.com/apache/couchdb).
* [Twisted](http://twistedmatrix.com/)
