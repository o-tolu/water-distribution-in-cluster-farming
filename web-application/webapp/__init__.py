try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    # PyMySQL is only required when using the optional MySQL database backend.
    pass
