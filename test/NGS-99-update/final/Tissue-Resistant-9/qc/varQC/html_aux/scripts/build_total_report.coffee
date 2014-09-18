sampleReport =
    sample:
        name: ''
        display_name: ''
        phenotype: ''
        bam: ''
        bed: ''
        vcf_by_caller:
            name: ''
            summary_qc_rep_fpaths: []
            anno_vcf_fpaths: {}
            anno_filt_vcf_fpaths: {}
    html_fpath: ''
    link: ''
    records: []

record =
    metric: null
    value: ''
    meta: null

metric =
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
    # lightness = Math.round (Math.pow hue - 75, 2) / 350 + 35
    lightness = 92
    return 'hsl(' + hue + ', 80%, ' + lightness + '%)'


all_values_equal = (vals) ->
    first_val = null
    for val in vals
        if first_val?
            if val != first_val
                return false
        else
            first_val = val
    return true


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

            for novelty, val_by_db of meta
                dbs = (db for db, val of val_by_db when db isnt 'average')
                dbs.push 'average'
                break

            short_table = true
            for novelty, val_by_db of meta
                if not all_values_equal(val for db, val of val_by_db when db isnt 'average')
                    short_table = false

            if short_table  # Values are the same for each database
                meta_table += '<tr><td></td>'
                for novelty, val_by_db of meta when novelty isnt 'all'
                    meta_table += "<td>#{toPrettyString(val_by_db[dbs[0]], rec.metric.unit)}</td>"
                meta_table += '</tr>\n'
            else
                for db in dbs
                    meta_table += "<tr><td>#{db}</td>"
                    for novelty, val_by_db of meta when novelty isnt 'all'
                        meta_table += "<td>#{toPrettyString(val_by_db[db], rec.metric.unit)}</td>"
                    meta_table += '</tr>\n'

            meta_table += '</table>\n'

            return "class=\"meta_info_span tooltip-meta\" rel=\"tooltip\" title=\"#{meta_table}\""
    else
        return "class=\"meta_info_span tooltip-meta\" rel=\"tooltip\""


get_metric_name_html = (metric, use_full_name=false) ->
    if metric.short_name and not use_full_name
        metricName = metric.short_name
        description = metric.description or metric.name
        return "<a class=\"tooltip-link\" rel=\"tooltip\" title=\"#{description}\">#{metricName}</a>"
    else
        return metric.name


calc_records_cell_contents = (records, font) ->
    for rec in records
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
        rec.frac_width = $.fn.intPartTextWidth num_html, font


calc_cell_contents = (report, section, font) ->
    max_frac_widths_by_metric = {}
    min_val_by_metric = {}
    max_val_by_metric = {}

    # First round: calculatings max/min integral/fractional widths (for decimal alingment) and max/min values (for heatmaps)
    for sampleReport in report.sample_reports
        calc_records_cell_contents sampleReport.records, font
        for rec in sampleReport.records when rec.metric.name of section.metrics_by_name
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

    # Second round: setting shift and color properties based on max/min widths and vals
    for sampleReport in report.sample_reports
        for rec in sampleReport.records when rec.metric.name of section.metrics_by_name
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
                    rec.metric.all_values_equal = true
#                    rec.color = get_color GREEN_HUE
                else
                    k = (maxHue - minHue) / (max - min)
                    hue = Math.round minHue + (rec.num - min) * k
                    rec.color = get_color hue


reporting.buildTotalReport = (report, section, columnOrder) ->
    if section.title?
        $('#report').append "<h3 class='table_name' style='margin: 0px 0 5px 0'>#{section.title}</h3>"

    calc_cell_contents report, section, $('#report').css 'font'

    table = "<table cellspacing=\"0\"
                    class=\"report_table tableSorter #{if DRAGGABLE_COLUMNS then 'draggable' else ''} fix-align-char\"
                    id=\"report_table_#{section.name}\">"
    table += "\n<tr class=\"top_row_tr\">"
    table += "<th class=\"top_left_td left_column_td\" data-sortBy='numeric'>
                    <span>Sample</span>
              </th>"

    for colNum in [0...section.metrics.length]
        pos = columnOrder[colNum]
        metric = section.metrics[pos]
        sort_by = if 'all_values_equal' of metric then 'nosort' else 'numeric'
        table += "<th class='second_through_last_col_headers_td' data-sortBy=#{sort_by} position='#{pos}'>
             <span class=\'metricName #{if DRAGGABLE_COLUMNS then 'drag_handle' else ''}\'>#{get_metric_name_html(metric)}</span>
        </th>"
        #{if DRAGGABLE_COLUMNS then '<span class=\'drag_handle\'><span class=\'drag_image\'></span></span>' else ''}

    i = 0
    for sampleReport in report.sample_reports
        line_caption = sampleReport.display_name  # sample name
        if line_caption.length > 30
            line_caption = "<span title=\"#{line_caption}\">#{line_caption.trunc(80)}</span>"

        table += "\n<tr>
            <td class=\"left_column_td\" data-sortAs=#{report.sample_reports.length - i}>"
        if report.sample_reports.length == 1
            table += "<span class=\"sample_name\">#{line_caption}</span>"
        else
            table += "<a class=\"sample_name\" href=\"#{sampleReport.html_fpath}\">#{line_caption}</a>"
        table += "</td>"

        records = (r for r in sampleReport.records when r.metric.name of section.metrics_by_name)
        for colNum in [0...section.metrics.length]
            pos = columnOrder[colNum]
            metric = section.metrics[pos]
            rec = records[pos]

            table += "<td metric=\"#{metric.name}\"
                          style=\"#{CSS_PROP_TO_COLOR}: #{rec.color}\"
                          class='number'
                          quality=\"#{metric.quality}\""
            if rec.num?
                table += " number=\"#{rec.value}\" data-sortAs=#{rec.value}>"
            else
                table += ">"

            if rec.right_shift?
                padding = "margin-left: #{rec.right_shift}px; margin-right: -#{rec.right_shift}px;"
            else
                padding = ""

            table += "<a style=\"#{padding}\"
                          #{get_meta_tag_contents(rec)}>#{rec.cell_contents}
                      </a>
                    </td>"
        table += "</tr>"
        i += 1
    table += "\n</table>\n"

    $('#report').append table


reporting.buildCommonRecords = (common_records) ->
    if common_records.length == 0
        return

    calc_records_cell_contents common_records, $('#report').css 'font'

    table = "<table cellspacing=\"0\" class=\"common_table\" id=\"common_table\">"
    for rec in common_records
        table += "\n<tr><td>
                <span class='metric_name'>#{get_metric_name_html(rec.metric, use_full_name=true)}:</span>
                #{rec.cell_contents}
              </td></tr>"
    table += "\n</table>\n"

    $('#report').append table


set_legend = ->
    legend = '<span>'
    step = 6
    for hue in [RED_HUE..GREEN_HUE] by step

        legend += "<span style=\"#{CSS_PROP_TO_COLOR}: #{get_color hue}\">"

        switch hue
            when RED_HUE              then legend += 'w'
            when RED_HUE   +     step then legend += 'o'
            when RED_HUE   + 2 * step then legend += 'r'
            when RED_HUE   + 3 * step then legend += 's'
            when RED_HUE   + 4 * step then legend += 't'
            when GREEN_HUE - 3 * step then legend += 'b'
            when GREEN_HUE - 2 * step then legend += 'e'
            when GREEN_HUE -     step then legend += 's'
            when GREEN_HUE            then legend += 't'
            else                           legend += '.'
        legend += "</span>"
    legend += "</span>"
    $('#report_legend').append legend


$.fn._splitDot_partTextWidth = (html, font, part_type) ->  # part_type = 'int'|'frac'
    parts = html.split '.'

    if part_type == 'frac'
        if parts.length < 2
            return 0
        else
            frac_part = '.' + parts[1]

    else if part_type == 'int'
        frac_part = parts[0]

    if (!$.fn.fracPartTextWidth.fakeEl)
        $.fn.fracPartTextWidth.fakeEl = $('<span>').hide().appendTo document.body

    $.fn.fracPartTextWidth.fakeEl.html frac_part
    $.fn.fracPartTextWidth.fakeEl.css 'font', font
    return $.fn.fracPartTextWidth.fakeEl.width()


$.fn.fracPartTextWidth = (html, font) ->
    $.fn._splitDot_partTextWidth html, font, 'frac'


$.fn.intPartTextWidth = (html, font) ->
    $.fn._splitDot_partTextWidth html, font, 'int'


$.fn.textWidth = (text, font) ->
    if (!$.fn.textWidth.fakeEl)
        $.fn.textWidth.fakeEl = $('<span>').hide().appendTo document.body

    $.fn.textWidth.fakeEl.html text
    $.fn.textWidth.fakeEl.css 'font', font
    return $.fn.textWidth.fakeEl.width()


String.prototype.trunc = (n) ->
    this.substr(0, n - 1) + (this.length > n ? '&hellip;': '')



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