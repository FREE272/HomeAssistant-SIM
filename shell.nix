{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = [ pkgs.python314 ];

  shellHook = ''
    export SSL_CERT_FILE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
    export PIP_CERT="$SSL_CERT_FILE"

    if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; assert sys.version_info >= (3, 14, 2)' >/dev/null 2>&1; then
      ${pkgs.python314}/bin/python -m venv --clear .venv
    elif [ ! -x .venv/bin/python ]; then
      ${pkgs.python314}/bin/python -m venv .venv
    fi

    source .venv/bin/activate
  '';
}
