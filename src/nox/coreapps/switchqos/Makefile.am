include ../../../Make.vars 

CONFIGURE_DEPENCIES = $(srcdir)/Makefile.am

EXTRA_DIST = \
	meta.json

pkglib_LTLIBRARIES =		\
	switchqos.la	

switchqos_la_CPPFLAGS = $(AM_CPPFLAGS) -I$(top_srcdir)/src/nox
switchqos_la_SOURCES = switchqos.cc
switchqos_la_LDFLAGS = -module -export-dynamic

NOX_RUNTIMEFILES = meta.json

all-local: nox-all-local
clean-local: nox-clean-local 
install-exec-hook: nox-install-local
