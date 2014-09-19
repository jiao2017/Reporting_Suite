import sys
import os
from  source.fastQC.HTML_Parser_FASTQC import get_graphs


def print_html(input_files):
    graphs = get_graphs(input_files)
    outfile = open("FASTQCSummary.html", "w")

    print >> outfile, """<html>
        <head>
    <title>FASTQC</title> """
    print >> outfile, print_css()
    print >> outfile, """
        </head>
        <body>
            <table border="1">"""


def print_graphs(outfile, graphs):
    i = 0
    while i < graphs.len():
        print >> outfile, "<tr>"

        print >> outfile, "</tr>"

        i += 1


def print_css():
    return """

    <style type="text/css">
        @media screen {
        div.summary {
        width: 18em;
        position:fixed;
        top: 3em;
        margin:1em 0 0 1em;
        }

        div.main {
        display:block;
        position:absolute;
        overflow:auto;
        height:auto;
        width:auto;
        top:4.5em;
        bottom:2.3em;
        left:18em;
        right:0;
        border-left: 1px solid #CCC;
        padding:0 0 0 1em;
        background-color: white;
        z-index:1;
        }

        div.header {
        background-color: #EEE;
        border:0;
        margin:0;
        padding: 0.5em;
        font-size: 200%;
        font-weight: bold;
        position:fixed;
        width:100%;
        top:0;
        left:0;
        z-index:2;
        }

        div.footer {
        background-color: #EEE;
        border:0;
        margin:0;
        padding:0.5em;
        height: 1.3em;
        overflow:hidden;
        font-size: 100%;
        font-weight: bold;
        position:fixed;
        bottom:0;
        width:100%;
        z-index:2;
        }

        img.indented {
        margin-left: 3em;
        }
        }

        @media print {
        img {
        max-width:100% !important;
        page-break-inside: avoid;
        }
        h2, h3 {
        page-break-after: avoid;
        }
        div.header {
        background-color: #FFF;
        }

        }

        body {
        font-family: sans-serif;
        color: #000;
        background-color: #FFF;
        border: 0;
        margin: 0;
        padding: 0;
        }

        div.header {
        border:0;
        margin:0;
        padding: 0.5em;
        font-size: 200%;
        font-weight: bold;
        width:100%;
        }

        #header_title {
        display:inline-block;
        float:left;
        clear:left;
        }
        #header_filename {
        display:inline-block;
        float:right;
        clear:right;
        font-size: 50%;
        margin-right:2em;
        text-align: right;
        }

        div.header h3 {
        font-size: 50%;
        margin-bottom: 0;
        }

        div.summary ul {
        padding-left:0;
        list-style-type:none;
        }

        div.summary ul li img {
        margin-bottom:-0.5em;
        margin-top:0.5em;
        }

        div.main {
        background-color: white;
        }

        div.module {
        padding-bottom:1.5em;
        padding-top:1.5em;
        }

        div.footer {
        background-color: #EEE;
        border:0;
        margin:0;
        padding: 0.5em;
        font-size: 100%;
        font-weight: bold;
        width:100%;
        }


        a {
        color: #000080;
        }

        a:hover {
        color: #800000;
        }

        h2 {
        color: #800000;
        padding-bottom: 0;
        margin-bottom: 0;
        clear:left;
        }

        table {
        margin-left: 3em;
        text-align: center;
        }

        th {
        text-align: center;
        background-color: #000080;
        color: #FFF;
        padding: 0.4em;
        }

        td {
        font-family: monospace;
        text-align: left;
        background-color: #EEE;
        color: #000;
        padding: 0.4em;
        }

        img {
        padding-top: 0;
        margin-top: 0;
        border-top: 0;
        }


        p {
        padding-top: 0;
        margin-top: 0;
        }
     </style> """

