{ nixpkgs ? import <nixpkgs> {  } }:

let
  pkgs = [
    nixpkgs.ripgrep
    nixpkgs.python3
    nixpkgs.python3.pkgs.requests
    nixpkgs.python3.pkgs.websockets
    nixpkgs.python3.pkgs.python-dotenv
    nixpkgs.python3.pkgs.jedi
    nixpkgs.python3.pkgs.pyyaml
  ];
 
in
  nixpkgs.stdenv.mkDerivation {
    name = "Python Bot";
    buildInputs = pkgs;
  }
