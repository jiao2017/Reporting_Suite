// Generated by CoffeeScript 1.7.1
(function() {
  var BLUE_HUE, BLUE_INNER_BRT, BLUE_OUTER_BRT, DRAGGABLE_COLUMNS, GREEN_HUE, GREEN_INNER_BRT, GREEN_OUTER_BRT, MEDIAN_BRT, MIN_NORMAL_BRT, RED_HUE, RED_INNER_BRT, RED_OUTER_BRT, calc_cell_contents, calc_record_cell_contents, check_all_values_equal, get_color, get_meta_tag_contents, get_metric_name_html, mean, median, metric, record, sampleReport,
    __hasProp = {}.hasOwnProperty;

  sampleReport = {
    sample: {
      name: '',
      display_name: '',
      phenotype: '',
      bam: '',
      bed: '',
      vcf_by_caller: {
        name: '',
        summary_qc_rep_fpaths: [],
        anno_vcf_fpaths: {},
        anno_filt_vcf_fpaths: {}
      }
    },
    html_fpath: '',
    link: '',
    records: []
  };

  record = {
    metric: null,
    value: '',
    meta: null,
    html_fpath: ''
  };

  metric = {
    name: '',
    short_name: '',
    description: '',
    quality: '',
    presision: 0,
    type: null,
    all_values_equal: false
  };

  DRAGGABLE_COLUMNS = false;

  BLUE_HUE = 240;

  BLUE_OUTER_BRT = 55;

  BLUE_INNER_BRT = 65;

  GREEN_HUE = 120;

  GREEN_OUTER_BRT = 50;

  GREEN_INNER_BRT = 60;

  RED_HUE = 0;

  RED_OUTER_BRT = 50;

  RED_INNER_BRT = 60;

  MIN_NORMAL_BRT = 80;

  MEDIAN_BRT = 100;

  get_color = function(hue, lightness) {
    var b, g, r, _ref;
    lightness = lightness != null ? lightness : 92;
    _ref = hslToRgb(hue / 360, 0.8, lightness / 100), r = _ref[0], g = _ref[1], b = _ref[2];
    return '#' + r.toString(16) + g.toString(16) + b.toString(16);
  };

  check_all_values_equal = function(vals) {
    var first_val, val, _i, _len;
    first_val = null;
    for (_i = 0, _len = vals.length; _i < _len; _i++) {
      val = vals[_i];
      if (first_val != null) {
        if (val !== first_val) {
          return false;
        }
      } else {
        first_val = val;
      }
    }
    return true;
  };

  get_meta_tag_contents = function(rec) {
    var a, db, dbs, k, meta, meta_table, novelty, pretty_str, short_table, val, val_by_db, values, _i, _len;
    meta = rec.meta;
    if ((meta != null) && ((function() {
      var _results;
      _results = [];
      for (a in meta) {
        _results.push(a);
      }
      return _results;
    })()).length !== 0) {
      if (typeof meta === 'string') {
        return "class=\"meta_info_span tooltip-meta\" rel=\"tooltip\" title=\"" + meta + "\"";
      } else {
        ((function() {
          var _results;
          _results = [];
          for (k in meta) {
            if (!__hasProp.call(meta, k)) continue;
            _results.push(k);
          }
          return _results;
        })()).length !== 0;
        meta_table = '<table class=\'qc_meta_table\'>\n<tr><td></td>';
        for (novelty in meta) {
          values = meta[novelty];
          if (novelty !== 'all') {
            meta_table += "<td>" + novelty + "</td>";
          }
        }
        meta_table += '</tr>\n';
        for (novelty in meta) {
          val_by_db = meta[novelty];
          dbs = (function() {
            var _results;
            _results = [];
            for (db in val_by_db) {
              val = val_by_db[db];
              if (db !== 'average') {
                _results.push(db);
              }
            }
            return _results;
          })();
          dbs.push('average');
          break;
        }
        short_table = true;
        for (novelty in meta) {
          val_by_db = meta[novelty];
          if (!check_all_values_equal((function() {
            var _results;
            _results = [];
            for (db in val_by_db) {
              val = val_by_db[db];
              if (db !== 'average') {
                _results.push(val);
              }
            }
            return _results;
          })())) {
            short_table = false;
          }
        }
        if (short_table) {
          meta_table += '<tr><td></td>';
          for (novelty in meta) {
            val_by_db = meta[novelty];
            if (!(novelty !== 'all')) {
              continue;
            }
            pretty_str = toPrettyString(val_by_db[dbs[0]], rec.metric.unit);
            meta_table += "<td>" + pretty_str + "</td>";
          }
          meta_table += '</tr>\n';
        } else {
          for (_i = 0, _len = dbs.length; _i < _len; _i++) {
            db = dbs[_i];
            meta_table += "<tr><td>" + db + "</td>";
            for (novelty in meta) {
              val_by_db = meta[novelty];
              if (novelty !== 'all') {
                meta_table += "<td>" + (toPrettyString(val_by_db[db], rec.metric.unit)) + "</td>";
              }
            }
            meta_table += '</tr>\n';
          }
        }
        meta_table += '</table>\n';
        return "class=\"meta_info_span tooltip-meta\" rel=\"tooltip\" title=\"" + meta_table + "\"";
      }
    } else {
      return "class=\"meta_info_span tooltip-meta\" rel=\"tooltip\"";
    }
  };

  get_metric_name_html = function(metric, use_full_name) {
    var description, metricName;
    if (use_full_name == null) {
      use_full_name = false;
    }
    if (metric.short_name && !use_full_name) {
      metricName = metric.short_name;
      description = metric.description || metric.name;
      return "<a class=\"metric_name\" rel=\"tooltip\" title=\"" + description + "\">" + metricName + "</a>";
    } else {
      return metric.name;
    }
  };

  calc_record_cell_contents = function(rec, font) {
    var num_html, result, value;
    value = rec.value;
    num_html = '';
    if ((value == null) || value === '') {
      rec.cell_contents = '-';
    } else {
      if (typeof value === 'number') {
        rec.num = value;
        rec.cell_contents = toPrettyString(value, rec.metric.unit);
        num_html = toPrettyString(value);
      } else if (/^-?.?[0-9]/.test(value)) {
        result = /([0-9\.]+)(.*)/.exec(value);
        rec.num = parseFloat(result[1]);
        rec.cell_contents = toPrettyString(rec.num, rec.metric.unit) + result[2];
        num_html = toPrettyString(rec.num);
      } else {
        rec.cell_contents = value;
      }
    }
    return rec.frac_width = $.fn.intPartTextWidth(num_html, font);
  };

  mean = function(a, b) {
    return (a + b) / 2;
  };

  calc_cell_contents = function(report, section, font) {
    var brt, d, inner_low_brt, inner_top_brt, k, l, low_hue, max_frac_widths_by_metric, outer_low_brt, outer_top_brt, q1, q3, rec, top_hue, vals, _i, _j, _k, _l, _len, _len1, _len2, _len3, _len4, _len5, _len6, _m, _n, _o, _ref, _ref1, _ref10, _ref11, _ref2, _ref3, _ref4, _ref5, _ref6, _ref7, _ref8, _ref9;
    max_frac_widths_by_metric = {};
    if ((report.type == null) || report.type === 'FullReport' || report.type === 'SquareSampleReport') {
      _ref = (report.hasOwnProperty('sample_reports') ? report.sample_reports : [report]);
      for (_i = 0, _len = _ref.length; _i < _len; _i++) {
        sampleReport = _ref[_i];
        _ref1 = sampleReport.records;
        for (_j = 0, _len1 = _ref1.length; _j < _len1; _j++) {
          rec = _ref1[_j];
          calc_record_cell_contents(rec, font);
        }
        _ref2 = sampleReport.records;
        for (_k = 0, _len2 = _ref2.length; _k < _len2; _k++) {
          rec = _ref2[_k];
          if (!(rec.metric.name in section.metrics_by_name)) {
            continue;
          }
          if (!(rec.metric.name in max_frac_widths_by_metric)) {
            max_frac_widths_by_metric[rec.metric.name] = rec.frac_width;
          } else if (rec.frac_width > max_frac_widths_by_metric[rec.metric.name]) {
            max_frac_widths_by_metric[rec.metric.name] = rec.frac_width;
          }
          if (rec.metric.values == null) {
            rec.metric.values = [];
          }
          rec.metric.values.push(rec.num);
        }
      }
    } else if (report.type === 'SampleReport') {
      _ref3 = sampleReport.records;
      for (_l = 0, _len3 = _ref3.length; _l < _len3; _l++) {
        rec = _ref3[_l];
        if (rec.metric.name in section.metrics_by_name) {
          if (rec.num != null) {
            if (rec.metric.values == null) {
              rec.metric.values = [];
            }
            rec.metric.values.push(rec.num);
          }
        }
      }
    }
    _ref4 = section.metrics;
    for (_m = 0, _len4 = _ref4.length; _m < _len4; _m++) {
      metric = _ref4[_m];
      if (!(metric.values != null)) {
        continue;
      }
      vals = metric.values.slice().sort(function(a, b) {
        if ((a != null) && (b != null)) {
          return a - b;
        } else if (a != null) {
          return a;
        } else {
          return b;
        }
      });
      l = vals.length;
      metric.min = vals[0];
      metric.max = vals[l - 1];
      metric.all_values_equal = metric.min === metric.max;
      metric.med = l % 2 !== 0 ? vals[(l - 1) / 2] : mean(vals[l / 2], vals[(l / 2) - 1]);
      q1 = vals[Math.floor((l - 1) / 4)];
      q3 = vals[Math.floor((l - 1) * 3 / 4)];
      d = q3 - q1;
      metric.low_outer_fence = q1 - 3 * d;
      metric.low_inner_fence = q1 - 1.5 * d;
      metric.top_inner_fence = q3 + 1.5 * d;
      metric.top_outer_fence = q3 + 3 * d;
    }
    _ref5 = (report.hasOwnProperty('sample_reports') ? report.sample_reports : [report]);
    for (_n = 0, _len5 = _ref5.length; _n < _len5; _n++) {
      sampleReport = _ref5[_n];
      _ref6 = sampleReport.records;
      for (_o = 0, _len6 = _ref6.length; _o < _len6; _o++) {
        rec = _ref6[_o];
        if (!(rec.metric.name in section.metrics_by_name)) {
          continue;
        }
        if (rec.frac_width != null) {
          rec.right_shift = max_frac_widths_by_metric[rec.metric.name] - rec.frac_width;
        }
        metric = rec.metric;
        if (rec.num != null) {
          _ref7 = [BLUE_HUE, BLUE_INNER_BRT, BLUE_OUTER_BRT], top_hue = _ref7[0], inner_top_brt = _ref7[1], outer_top_brt = _ref7[2];
          _ref8 = [RED_HUE, RED_INNER_BRT, RED_OUTER_BRT], low_hue = _ref8[0], inner_low_brt = _ref8[1], outer_low_brt = _ref8[2];
          if (metric.quality === 'Less is better') {
            _ref9 = [low_hue, top_hue], top_hue = _ref9[0], low_hue = _ref9[1];
            _ref10 = [inner_low_brt, inner_top_brt], inner_top_brt = _ref10[0], inner_low_brt = _ref10[1];
            _ref11 = [outer_low_brt, outer_top_brt], outer_top_brt = _ref11[0], outer_low_brt = _ref11[1];
          }
          if (!metric.all_values_equal) {
            rec.text_color = 'black';
            if (rec.num < rec.metric.low_outer_fence) {
              rec.color = get_color(low_hue, outer_low_brt);
              rec.text_color = 'white';
            } else if (rec.num < rec.metric.low_inner_fence) {
              rec.color = get_color(low_hue, inner_low_brt);
            } else if (rec.num < metric.med) {
              k = (MEDIAN_BRT - MIN_NORMAL_BRT) / (metric.med - rec.metric.low_inner_fence);
              brt = Math.round(MEDIAN_BRT - (metric.med - rec.num) * k);
              rec.color = get_color(low_hue, brt);
            } else if (rec.num > rec.metric.top_inner_fence) {
              rec.color = get_color(top_hue, inner_top_brt);
            } else if (rec.num > rec.metric.top_outer_fence) {
              rec.color = get_color(top_hue, outer_top_brt);
              rec.text_color = 'white';
            } else if (rec.num > metric.med) {
              k = (MEDIAN_BRT - MIN_NORMAL_BRT) / (rec.metric.top_inner_fence - metric.med);
              brt = Math.round(MEDIAN_BRT - (rec.num - metric.med) * k);
              rec.color = get_color(top_hue, brt);
            }
          }
        }
      }
    }
    return report;
  };

  median = function(x) {
    var sorted;
    if (x.length === 0) {
      return null;
    }
    sorted = x.slice().sort(function(a, b) {
      return a - b;
    });
    if (sorted.length % 2 === 1) {
      return sorted[(sorted.length - 1) / 2];
    } else {
      return (sorted[(sorted.length / 2) - 1] + sorted[sorted.length / 2]) / 2;
    }
  };

  reporting.buildTotalReport = function(report, section, columnOrder) {
    var caller, caller_links, colNum, direction, html_fpath, i, k, line_caption, links, max_sample_name_len, padding, pos, r, rec, report_name, sample_reports_length, second_row_tr, sort_by, table, _i, _j, _k, _l, _len, _len1, _ref, _ref1, _ref2, _ref3, _ref4, _ref5;
    if (section.title != null) {
      $('#report').append("<h3 class='table_name'>" + section.title + "</h3>");
    }
    calc_cell_contents(report, section, $('#report').css('font'));
    table = "<table cellspacing=\"0\" class=\"report_table tableSorter " + (DRAGGABLE_COLUMNS ? 'draggable' : '') + " fix-align-char\" id=\"report_table_" + section.name + "\">";
    table += "\n<thead><tr class=\"top_row_tr\">";
    table += "<th class=\"top_left_td left_column_td\" data-sortBy='numeric'> <span>Sample</span> </th>";
    for (colNum = _i = 0, _ref = section.metrics.length; 0 <= _ref ? _i < _ref : _i > _ref; colNum = 0 <= _ref ? ++_i : --_i) {
      pos = columnOrder[colNum];
      metric = section.metrics[pos];
      sort_by = metric.all_values_equal ? 'nosort' : 'numeric';
      direction = metric.quality === 'Less is better' ? 'ascending' : 'descending';
      table += "<th class='second_through_last_col_headers_td' data-sortBy=" + sort_by + " data-direction=" + direction + "position='" + pos + "'> <span class=\'metricName " + (DRAGGABLE_COLUMNS ? 'drag_handle' : '') + "\'>" + (get_metric_name_html(metric)) + "</span> </th>";
    }
    table += '</tr></thead><tbody>';
    i = 0;
    sample_reports_length = report.hasOwnProperty('sample_reports') ? report.sample_reports.length : 1;
    _ref1 = (report.hasOwnProperty('sample_reports') ? report.sample_reports : [report]);
    for (_j = 0, _len = _ref1.length; _j < _len; _j++) {
      sampleReport = _ref1[_j];
      line_caption = sampleReport.display_name;
      max_sample_name_len = 50;
      if (line_caption.length > max_sample_name_len) {
        line_caption = "<span title=\"" + line_caption + "\">" + (line_caption.substring(0, max_sample_name_len)) + "...</span>";
      }
      second_row_tr = i === 0 ? "second_row_tr" : "";
      table += "\n<tr class=\"" + second_row_tr + "\"> <td class=\"left_column_td td\" data-sortAs=" + (sample_reports_length - i) + ">";
      if (sample_reports_length === 1) {
        table += "<span class=\"sample_name\">" + line_caption + "</span>";
      } else {
        if (sampleReport.html_fpath != null) {
          if (typeof sampleReport.html_fpath === 'string') {
            table += "<a class=\"sample_name\" href=\"" + sampleReport.html_fpath + "\">" + line_caption + "</a>";
          } else {
            if (((function() {
              var _ref2, _results;
              _ref2 = sampleReport.html_fpath;
              _results = [];
              for (k in _ref2) {
                if (!__hasProp.call(_ref2, k)) continue;
                _results.push(k);
              }
              return _results;
            })()).length === 0) {
              table += "<span class=\"sample_name\"\">" + line_caption + "</span>";
            } else {
              links = "";
              _ref2 = sampleReport.html_fpath;
              for (report_name in _ref2) {
                html_fpath = _ref2[report_name];
                if (links.length !== 0) {
                  links += ", ";
                }
                links += "<a href=\"" + html_fpath + "\">" + report_name + "</a>";
              }
              table += "<span class=\"sample_name\"\">" + line_caption + " (" + links + ")</span>";
            }
          }
        } else {
          table += "<span class=\"sample_name\"\">" + line_caption + "</span>";
        }
      }
      table += "</td>";
      for (colNum = _k = 0, _ref3 = section.metrics.length; 0 <= _ref3 ? _k < _ref3 : _k > _ref3; colNum = 0 <= _ref3 ? ++_k : --_k) {
        pos = columnOrder[colNum];
        metric = section.metrics[pos];
        rec = null;
        _ref4 = sampleReport.records;
        for (_l = 0, _len1 = _ref4.length; _l < _len1; _l++) {
          r = _ref4[_l];
          if (r.metric.name === metric.name) {
            rec = r;
            break;
          }
        }
        if (rec == null) {
          table += "<td></td>";
          continue;
        }
        table += "<td metric=\"" + metric.name + "\" style=\"background-color: " + rec.color + "; color: " + rec.text_color + "\" quality=\"" + metric.quality + "\" class='td ";
        if (rec.num != null) {
          table += " number' number=\"" + rec.value + "\" data-sortAs=" + rec.value + ">";
        } else {
          table += "'>";
        }
        if (rec.right_shift != null) {
          padding = "margin-left: " + rec.right_shift + "px; margin-right: -" + rec.right_shift + "px;";
        } else {
          padding = "";
        }
        if (rec.html_fpath != null) {
          if (typeof rec.html_fpath === 'string') {
            table += "<a href=\"" + rec.html_fpath + "\">" + rec.cell_contents + " </a> </td>";
          } else {
            if (((function() {
              var _ref5, _results;
              _ref5 = rec.html_fpath;
              _results = [];
              for (k in _ref5) {
                if (!__hasProp.call(_ref5, k)) continue;
                _results.push(k);
              }
              return _results;
            })()).length === 0) {
              rec.value = null;
              calc_record_cell_contents(rec, $('#report').css('font'));
              table += "" + rec.cell_contents + "</td>";
            } else {
              caller_links = "";
              _ref5 = rec.html_fpath;
              for (caller in _ref5) {
                html_fpath = _ref5[caller];
                if (caller_links.length !== 0) {
                  caller_links += ", ";
                }
                caller_links += "<a href=\"" + html_fpath + "\">" + caller + "</a>";
              }
              table += "" + rec.cell_contents + " (" + caller_links + ")</td>";
            }
          }
        } else {
          table += "<a style=\"" + padding + "\" " + (get_meta_tag_contents(rec)) + ">" + rec.cell_contents + " </a> </td>";
        }
      }
      table += "</tr>";
      i += 1;
    }
    table += "\n</tbody></table>\n";
    return $('#report').append(table);
  };

  reporting.buildCommonRecords = function(common_records) {
    var rec, table, use_full_name, _i, _j, _len, _len1;
    if (common_records.length === 0) {
      return;
    }
    for (_i = 0, _len = common_records.length; _i < _len; _i++) {
      rec = common_records[_i];
      calc_record_cell_contents(rec, $('#report').css('font'));
    }
    table = "<table cellspacing=\"0\" class=\"common_table\" id=\"common_table\">";
    for (_j = 0, _len1 = common_records.length; _j < _len1; _j++) {
      rec = common_records[_j];
      table += "\n<tr><td>";
      if (rec.html_fpath != null) {
        table += "<a href=\"" + rec.html_fpath + "\"> " + rec.cell_contents + "</a>";
      } else {
        table += "<span class='metric_name'>" + (get_metric_name_html(rec.metric, use_full_name = true)) + ":</span> " + rec.cell_contents;
      }
      table += "</td></tr>";
    }
    table += "\n</table>\n";
    table += "<div class='space_30px'></div>";
    return $('#report').append(table);
  };

  $.fn._splitDot_partTextWidth = function(html, font, part_type) {
    var frac_part, parts;
    parts = html.split('.');
    if (part_type === 'frac') {
      if (parts.length < 2) {
        return 0;
      } else {
        frac_part = '.' + parts[1];
      }
    } else if (part_type === 'int') {
      frac_part = parts[0];
    }
    if (!$.fn.fracPartTextWidth.fakeEl) {
      $.fn.fracPartTextWidth.fakeEl = $('<span>').hide().appendTo(document.body);
    }
    $.fn.fracPartTextWidth.fakeEl.html(frac_part);
    $.fn.fracPartTextWidth.fakeEl.css('font', font);
    return $.fn.fracPartTextWidth.fakeEl.width();
  };

  $.fn.fracPartTextWidth = function(html, font) {
    return $.fn._splitDot_partTextWidth(html, font, 'frac');
  };

  $.fn.intPartTextWidth = function(html, font) {
    return $.fn._splitDot_partTextWidth(html, font, 'int');
  };

  $.fn.textWidth = function(text, font) {
    if (!$.fn.textWidth.fakeEl) {
      $.fn.textWidth.fakeEl = $('<span>').hide().appendTo(document.body);
    }
    $.fn.textWidth.fakeEl.html(text);
    $.fn.textWidth.fakeEl.css('font', font);
    return $.fn.textWidth.fakeEl.width();
  };

  String.prototype.trunc = function(n) {
    var _ref;
    return this.substr(0, n - 1) + ((_ref = this.length > n) != null ? _ref : {
      '&hellip;': ''
    });
  };

}).call(this);

//# sourceMappingURL=build_total_report.map
