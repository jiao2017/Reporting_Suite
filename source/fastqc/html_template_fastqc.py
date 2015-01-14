import sys
import itertools
from source import verify_file
from source.fastqc.html_parser_fastqc import get_graphs


def print_html(a_outfile, samples):
    graphs = get_graphs(samples)
    with open(a_outfile, 'w') as outfile:
        print >> outfile, """<html> <head> <title>FASTQC</title> """
        print >> outfile, print_js()
        print >> outfile, print_css()
        print >> outfile, """ </head> <body>"""
        links_show_hide(outfile, samples)
        print_graphs(outfile, graphs)
        print >> outfile, """ </body> </html>"""


def print_graphs(outfile, graphs):
    print >> outfile, '<table >'

    for graph_name, values in graphs.items():
        print >> outfile, '<tr class="title" ><td colspan=" ' + str(
            len(values)) + '"><h2 >' + graph_name + '</h2><td></tr>'
        print >> outfile, '<tr >'
        i = 0
        for div_contains in values:
            bam_file_name = div_contains[0]
            ok_img = div_contains[1]
            graph = div_contains[2]
            table = div_contains[3]
            print >> outfile, '<td  name="tcol' + str(i) + '"  id="tcol' + str(i) + '"  class="data">' + str(
                ok_img) + str(bam_file_name) + '</br>' + str(graph) + str(table) + '</td>'
            i += 1
        print >> outfile, '</tr>'

    print >> outfile, '</table>'


def none_type_validation(obj):
    if obj is None:
        return ""
    else:
        return str(obj)


def print_to_html(outfile, text_to_html):
    print >> outfile, text_to_html


def group2(iterator, count):
    if count > len(iterator): count = len(iterator)
    return itertools.imap(None, *([iter(iterator)] * count))


def chunks(l, n):
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


def links_show_hide(outfile, s_names):
    print >> outfile, '<form name="tcol" onsubmit="return false">  Show columns <br/>'
    print >> outfile, '<table>'
    i = 0

    list_of_chunks = list(chunks([s.fastqc_html_fpath for s in s_names if verify_file(s.fastqc_html_fpath)], 6))
   
    for s_names in list_of_chunks:
        print >> outfile, '<tr>'
        for sample in s_names:
            print >> outfile, '<td><input type=checkbox name="col' + str(i) + '"  onclick="toggleVis(' + str(
                i) + ')" checked> ' + sample + '</td>'
            i += 1
        print >> outfile, '</tr>'
    print >> outfile, '</table>'
    print >> outfile, '</form> '


def print_js():
    return """
    <script src="../../combined_report/html_aux/jquery-1.8.2.min.js"
        type="text/javascript"></script>
    <script>



    $(document).ready(function(){
      $("img.indented").click(function resize() {
            if ($("img.indented").height() == 500) {
                $("img.indented").width(300);
                $("img.indented").height(300);
            }
            else {
                $("img.indented").width(500);
                $("img.indented").height(500);
            }
             return false;
        });
    });

            var showMode = 'table-cell';

            // However, IE5 at least does not render table cells correctly
            // using the style 'table-cell', but does when the style 'block'
            // is used, so handle this

            if (document.all) showMode='block';

            // This is the function that actually does the manipulation

    function toggleVis(btn){
            // First isolate the checkbox by name using the
            // name of the form and the name of the checkbox

            btn   = document.forms['tcol'].elements[btn];

            // Next find all the table cells by using the DOM function
            // getElementsByName passing in the constructed name of
            // the cells, derived from the checkbox name

            cells = document.getElementsByName('t'+btn.name);

            // Once the cells and checkbox object has been retrieved
            // the show hide choice is simply whether the checkbox is
            // checked or clear

            //	mode = btn.checked ? showMode : 'none';

            // Apply the style to the CSS display property for the cells

            for(j = 0; j < cells.length; j++) $(cells[j]).toggle("slide");  //cells[j].style.display = mode;
    }

</script> """


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
        width:300;
        height:300;
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
        background-color: #ADD8E6;
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

        tr.title {
        background-color: #F0E68C;
        }

        td {
        font-family: monospace;
        vertical-align: top;
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


if __name__ == "__main__":
    print_html(sys.argv[1], sys.argv[2:])

