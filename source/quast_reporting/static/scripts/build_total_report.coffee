report =
    sample:
        name: ''
        phenotype: ''
        bam: ''
        bed: ''
        vcf_by_caller:
            name: ''
            summary_qc_rep_fpaths: []
            anno_vcf_fpaths: {}
            anno_filt_vcf_fpaths: {}
    fpath: ''
    link: ''
    records: []

records =
    metric: null
    value: ''
    meta: null

metricName =
    name: ''
    short_name: ''
    description: ''
    quality: ''
    presision: 0
    type: null


DRAGGABLE_COLUMNS = false

RED_HUE = 0
GREEN_HUE = 120
GREEN_HSL = 'hsl(' + GREEN_HUE + ', 80%, 40%)'
CSS_PROP_TO_COLOR = 'background-color'  # color
get_color = (hue) ->
    # lightness = Math.round (Math.pow hue - 75, 2) / 350 + 75
    # lightness = Math.round (Math.pow hue - 75, 2) / 350 + 35
    lightness = 92
    return 'hsl(' + hue + ', 80%, ' + lightness + '%)'


get_meta_tag_contents = (rec) ->
    meta = rec.meta

    if meta? and (a for a of meta).length != 0
        if typeof meta is 'string'
            return "class=\"meta_info_span tooltip-meta\" rel=\"tooltip\" title=\"#{meta}\""

        else  # qc
            (k for own k of meta).length isnt 0
            meta_table = '<table class=\'qc_meta_table\'>\n<tr><td></td>'
            for novelty, values of meta when novelty isnt 'all'
                meta_table += "<td>#{novelty}</td>"
            meta_table += '</tr>\n'

            for novelty, values of meta
                dbs = (db for db, val of values when db isnt 'average')
                dbs.push 'average'
                break

            for db in dbs
                meta_table += "<tr><td>#{db}</td>"
                for novelty, values of meta when novelty isnt 'all'
                    meta_table += "<td>#{toPrettyString(values[db], rec.metric.unit)}</td>"

                meta_table += '</tr>\n'
            meta_table += '</table>\n'

            return "class=\"meta_info_span tooltip-meta\" rel=\"tooltip\" title=\"#{meta_table}\""
    else
        return "class=\"meta_info_span tooltip-meta\" rel=\"tooltip\""


calc_cell_contents = (report, font) ->
    max_frac_widths_by_metric = {}
    min_val_by_metric = {}
    max_val_by_metric = {}

    for sampleReport in report
        for rec in sampleReport.records
            value = rec.value
            num_html = ''

            if not value? or value == ''
                rec.cell_contents = '-'

            else
                if typeof value == 'number'
                    rec.num = value
                    rec.cell_contents = toPrettyString value, rec.metric.unit
                    num_html = toPrettyString value

                else if /^-?.?[0-9]/.test(value)
                    result = /([0-9\.]+)(.*)/.exec value
                    rec.num = parseFloat result[1]
                    rec.cell_contents = toPrettyString(rec.num, rec.metric.unit) + result[2]
                    num_html = toPrettyString(rec.num)
                else
                    rec.cell_contents = value

            # Max frac width of column
            rec.frac_width = $.fn.fracPartTextWidth num_html, font

            if not (rec.metric.name of max_frac_widths_by_metric)
                max_frac_widths_by_metric[rec.metric.name] = rec.frac_width
            else if rec.frac_width > max_frac_widths_by_metric[rec.metric.name]
                max_frac_widths_by_metric[rec.metric.name] = rec.frac_width

            # Max and min value (for heatmap)
            if rec.num?
                if not (rec.metric.name of min_val_by_metric)
                    min_val_by_metric[rec.metric.name] = rec.num
                else if min_val_by_metric[rec.metric.name] > rec.num
                    min_val_by_metric[rec.metric.name] = rec.num

                if not (rec.metric.name of max_val_by_metric)
                    max_val_by_metric[rec.metric.name] = rec.num
                else if max_val_by_metric[rec.metric.name] < rec.num
                    max_val_by_metric[rec.metric.name] = rec.num

    for sampleReport in report
        for rec in sampleReport.records
            # Padding based on frac width
            if rec.frac_width?
                rec.right_shift = max_frac_widths_by_metric[rec.metric.name] - rec.frac_width

                if rec.right_shift != 0
                    a = 0

            # Color heatmap
            if rec.num?
                max = max_val_by_metric[rec.metric.name]
                min = min_val_by_metric[rec.metric.name]

                maxHue = GREEN_HUE
                minHue = RED_HUE
                if rec.metric.quality == 'Less is better'
                    maxHue = RED_HUE
                    minHue = GREEN_HUE

                if max == min
#                    rec.color = get_color GREEN_HUE
                else
                    k = (maxHue - minHue) / (max - min)
                    hue = Math.round minHue + (rec.num - min) * k
                    rec.color = get_color hue


reporting.buildTotalReport = (report, columnOrder, date) ->
    $('#report_date').html('<p>' + date + '</p>');

    calc_cell_contents report, $('#report').css 'font'

    table = "<table cellspacing=\"0\" class=\"report_table #{if DRAGGABLE_COLUMNS then 'draggable' else ''} fix-align-char\" id=\"main_report_table\">"
    table += "\n<tr class=\"top_row_tr\">"
    table += "<td id=\"top_left_td\" class=\"left_column_td\">
                <span>Sample</span>
              </td>"

    for recNum in [0...report[0].records.length]
        pos = columnOrder[recNum]
        rec = report[0].records[pos]
        if metricName.description
            metricHtml = "<a class=\"tooltip-link\" rel=\"tooltip\" title=\"#{rec.metric.description}\">
                #{rec.metric.short_name}
            </a>"
        else
            if metricName.short_name is undefined
                metricHtml = rec.metric.name
            else
                metricHtml = rec.metric.short_name

        table += "<td class='second_through_last_col_headers_td' position='#{pos}'>
             #{if DRAGGABLE_COLUMNS then '<span class=\'drag_handle\'><span class=\'drag_image\'></span></span>' else ''}
             <span class='metricName'>#{metricHtml}</span>
        </td>"

    for sampleReport in report
        sampleName = sampleReport.sample.name
        sampleLink = sampleReport.link
        if sampleName.length > 30
            sampleName = "<span title=\"#{sampleName}\">#{sampleName.trunc(80)}</span>"

        table += "\n<tr>
            <td class=\"left_column_td\">
                <a class=\"sample_name\" href=\"#{sampleLink}\">#{sampleName}</a>
            </td>"

        for recNum in [0...sampleReport.records.length]
            pos = columnOrder[recNum]
            rec = sampleReport.records[pos]

            table += "<td metric=\"#{rec.metric.name}\"
                          style=\"#{CSS_PROP_TO_COLOR}: #{rec.color}\"
                          class='number'
                          quality=\"#{rec.metric.quality}\""
            if rec.num? then table += ' number="' + rec.value + '">'
            if rec.right_shift?
                padding = "margin-right: #{rec.right_shift}px; margin-left: -#{rec.right_shift}px;"
            else
                padding = ""
            table += "<a style=\"#{padding}\"
                          #{get_meta_tag_contents(rec)}>#{rec.cell_contents}
                      </a>
                      </td>"
        table += "</tr>"
    table += "\n</table>\n"

    $('#report').append table


#set_offset = (all_cells, all_numbers, metricName) ->
#    if (num for num in all_numbers when isFractional num).length == 0
#        console.log 'Integer: ' + metricName
#    else
#        console.log 'Decimal: ' + metricName
#
#        # Floating point: decimal point alignment
#        left_part_widths = []
#        max_left_part_width = 0
#        for cell in $(all_cells)
#            text = $(cell).text()
#            parts = text.split '.'
#            left = parts[parts.length - 1]
#
#            left_part = if left? and left != 'undefined' then '.' + left else left_part = ''
#
#            width = $.fn.textWidth left_part, $(cell).css 'font'
#            left_part_widths.push width
#            max_left_part_width = width if width > max_left_part_width
#
#            # if (w for w in left_part_widths when w != max_left_part_width).length > 0
#            #    console.log 'max_left_part_width: ' + max_left_part_width
#
#        for i in [0...left_part_widths.length]
#            left_part_width = left_part_widths[i]
#            if max_left_part_width != left_part_width
#                cell = $(all_cells[i])
#                a = cell.children('a')
#                padding = a.css 'margin-right'
#                padding += (max_left_part_width + left_part_width) + 'px'
#                a.css 'margin-right', padding
#                padding = a.css 'margin-right'


set_legend = ->
    legend = '<span>'
    step = 6
    for hue in [RED_HUE..GREEN_HUE] by step

        legend += "<span style=\"#{CSS_PROP_TO_COLOR}: #{get_color hue}\">"

        switch hue
            when RED_HUE              then legend += 'w'
            when RED_HUE   + step     then legend += 'o'
            when RED_HUE   + 2 * step then legend += 'r'
            when RED_HUE   + 3 * step then legend += 's'
            when RED_HUE   + 4 * step then legend += 't'
            when GREEN_HUE - 3 * step then legend += 'b'
            when GREEN_HUE - 2 * step then legend += 'e'
            when GREEN_HUE - step     then legend += 's'
            when GREEN_HUE            then legend += 't'
            else                           legend += '.'
        legend += "</span>"
    legend += "</span>"
    $('#report_legend').append legend


$.fn.fracPartTextWidth = (html, font) ->
    parts = html.split '.'
    if parts.length > 1
        frac_part = '.' + parts[parts.length - 1]
        if (!$.fn.fracPartTextWidth.fakeEl)
            $.fn.fracPartTextWidth.fakeEl = $('<span>').hide().appendTo document.body

        $.fn.fracPartTextWidth.fakeEl.html frac_part
        $.fn.fracPartTextWidth.fakeEl.css 'font', font
        return $.fn.fracPartTextWidth.fakeEl.width()
    else
        return 0


$.fn.textWidth = (text, font) ->
    if (!$.fn.textWidth.fakeEl)
        $.fn.textWidth.fakeEl = $('<span>').hide().appendTo document.body

    $.fn.textWidth.fakeEl.html text
    $.fn.textWidth.fakeEl.css 'font', font
#    $.fn.textWidth.fakeEl.text($.fn.fracPartTextWidth.fakeEl.text())
    return $.fn.textWidth.fakeEl.width()


#postprocess_cells = ->
#    processes_metrics = []
#
#    $(".report_table td[number]").each ->
#        metricName = $(this).attr 'metricName'
#
#        if !(metricName in processes_metrics)
#            processes_metrics.push metricName
#            console.log metricName
#
#            quality = $(this).attr 'quality'
#            all_cells = $('.report_table').find "td[metricName=\"#{metricName}\"][number]"
#            all_numbers = ($(cell).attr 'number' for cell in all_cells)
#
#            set_heatmap all_cells, all_numbers, quality
#
#            set_offset all_cells, all_numbers, metricName


String.prototype.trunc = (n) ->
    this.substr(0, n - 1) + (this.length > n ? '&hellip;': '')
