# Security policy

Report vulnerabilities through this repository's **Security → Report a
vulnerability** form. This creates a private security advisory; do not put
exploit details, device identifiers, or logs in a public issue.

Before the first public release, repository maintainers must enable **Settings
→ Code security and analysis → Private vulnerability reporting**. If the
reporting button is unavailable, open a public issue containing no sensitive
details and ask the maintainer to provide a private contact channel.

The application does not listen on a network port, capture keystrokes, or run a
privileged daemon. The GNOME integration stores only configured accelerators
and commands. Device access is delegated to Solaar and the operating system's
udev permissions.

Never install a world-writable Logitech hidraw rule such as `MODE="0666"` for
this application. Use the distribution's Solaar rule, which grants access to
the active local session.

Run the application as the logged-in desktop user, never with `sudo`. Config
files and executable overrides must live at trusted, non-group/world-writable
paths. Host-change timeouts have an uncertain outcome and must not be retried
automatically or immediately. Check the destination host first, then use the
physical Easy-Switch button if the mouse is unreachable.
