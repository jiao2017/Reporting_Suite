// Generated by CoffeeScript 1.7.1
(function() {
  var GREEN_HSL, GREEN_HUE, RED_HUE, heatmap, hue, legend, lightness, metric, report, step, _i;

  String.prototype.trunc = function(n) {
    var _ref;
    return this.substr(0, n - 1) + ((_ref = this.length > n) != null ? _ref : {
      '&hellip;': ''
    });
  };

  report = {
    name: '',
    fpath: '',
    metrics: []
  };

  metric = {
    name: '',
    quality: '',
    value: '',
    meta: ''
  };

  reporting.buildTotalReport = function(report, columnOrder, date, glossary) {
    var db, dbs, meta, metricNum, novelty, num, pos, quality, rest, result, sampleName, sampleReport, table, val, value, values, _i, _j, _k, _l, _len, _len1, _ref, _ref1, _ref2, _ref3, _ref4;
    $('#report_date').html('<p>' + date + '</p>');
    table = '<table cellspacing="0" class="report_table draggable" id="main_report_table">';
    table += '<tr class="top_row_tr"> <td id="top_left_td" class="left_column_td"> <span>Sample</span> </td>';
    for (metricNum = _i = 0, _ref = report[0].metrics.length; 0 <= _ref ? _i < _ref : _i > _ref; metricNum = 0 <= _ref ? ++_i : --_i) {
      pos = columnOrder[metricNum];
      metric = report[0].metrics[pos];
      table += '<td class="second_through_last_col_headers_td" position="' + pos + '">' + '<span class="drag_handle"><span class="drag_image"></span></span>' + '<span class="metric_name" quality="' + metric.quality + '">' + nbsp(addTooltipIfDefinitionExists(glossary, metric.name), metric.name) + '</span> </td>';
    }
    for (_j = 0, _len = report.length; _j < _len; _j++) {
      sampleReport = report[_j];
      sampleName = sampleReport.name;
      if (sampleReport.name.length > 30) {
        sampleName = '<span class="tooltip-link" rel="tooltip" title="' + sampleName + '">' + sampleName.trunc(80) + '</span>';
      }
      table += '<tr><td class="left_column_td"><span class="sample_name">' + sampleName + '</span></td>';
      for (metricNum = _k = 0, _ref1 = sampleReport.metrics.length; 0 <= _ref1 ? _k < _ref1 : _k > _ref1; metricNum = 0 <= _ref1 ? ++_k : --_k) {
        pos = columnOrder[metricNum];
        metric = sampleReport.metrics[pos];
        quality = metric.quality;
        value = metric.value;
        if (metric.meta != null) {
          meta = '<table class=\'qc_meta_table\'>\n<tr><td></td>';
          _ref2 = metric.meta;
          for (novelty in _ref2) {
            values = _ref2[novelty];
            meta += '<td>' + novelty + '</td>';
          }
          meta += '</tr>\n';
          _ref3 = metric.meta;
          for (novelty in _ref3) {
            values = _ref3[novelty];
            dbs = (function() {
              var _results;
              _results = [];
              for (db in values) {
                val = values[db];
                _results.push(db);
              }
              return _results;
            })();
            break;
          }
          for (_l = 0, _len1 = dbs.length; _l < _len1; _l++) {
            db = dbs[_l];
            meta += '<tr>' + '<td>' + db + '</td>';
            _ref4 = metric.meta;
            for (novelty in _ref4) {
              values = _ref4[novelty];
              meta += '<td>' + values[db] + '</td>';
            }
            meta += '</tr>\n';
          }
          meta += '</table>\n';
        }
        if ((value == null) || value === '') {
          table += '<td><span>-</span></td>';
        } else if (typeof value === 'number') {
          table += '<td number="' + value + '"><span class="meta_info_span" rel="tooltip" title="' + meta + '">' + toPrettyString(value) + '</span></td>';
        } else {
          result = /([0-9\.]+)(.*)/.exec(value);
          num = parseFloat(result[1]);
          rest = result[2];
          if (num != null) {
            table += '<td number="' + num + '"><span class="meta_info_span" rel="tooltip" title="' + meta + '">' + toPrettyString(num) + rest + '</span></td>';
          } else {
            table += '<td><span class="meta_info_span" rel="tooltip" title="' + meta + '">' + value + '</span></td>';
          }
        }
      }
      table += '</tr>';
    }
    table += '</table>';
    $('#report').append(table);
    $('#report_legend').append(legend);
    return heatmap();
  };

  RED_HUE = 0;

  GREEN_HUE = 120;

  GREEN_HSL = 'hsl(' + GREEN_HUE + ', 80%, 40%)';

  legend = '<span>';

  step = 6;

  for (hue = _i = RED_HUE; step > 0 ? _i <= GREEN_HUE : _i >= GREEN_HUE; hue = _i += step) {
    lightness = (Math.pow(hue - 75, 2)) / 350 + 35;
    legend += '<span style="color: hsl(' + hue + ', 80%, ' + lightness + '%);">';
    switch (hue) {
      case RED_HUE:
        legend += 'w';
        break;
      case RED_HUE + step:
        legend += 'o';
        break;
      case RED_HUE + 2 * step:
        legend += 'r';
        break;
      case RED_HUE + 3 * step:
        legend += 's';
        break;
      case RED_HUE + 4 * step:
        legend += 't';
        break;
      case GREEN_HUE - 3 * step:
        legend += 'b';
        break;
      case GREEN_HUE - 2 * step:
        legend += 'e';
        break;
      case GREEN_HUE - step:
        legend += 's';
        break;
      case GREEN_HUE:
        legend += 't';
        break;
      default:
        legend += '.';
    }
    legend += '</span>';
  }

  legend += '</span>';

  heatmap = function() {
    return $(".report_table td[number]").each(function() {
      var cells, k, max, maxHue, min, minHue, numbers, quality;
      cells = $(this).parent().find('td[number]');
      numbers = $.map(cells, function(cell) {
        return $(cell).attr('number');
      });
      quality = $(this).parent().attr('quality');
      min = Math.min.apply(null, numbers);
      max = Math.max.apply(null, numbers);
      maxHue = GREEN_HUE;
      minHue = RED_HUE;
      if (quality === 'Less is better') {
        maxHue = RED_HUE;
        minHue = GREEN_HUE;
      }
      if (max === min) {
        return $(cells).css('color', GREEN_HSL);
      } else {
        k = (maxHue - minHue) / (max - min);
        hue = 0;
        lightness = 0;
        return cells.each(function(i) {
          var number;
          number = numbers[i];
          hue = Math.round(minHue + (number - min) * k);
          lightness = Math.round((Math.pow(hue - 75, 2)) / 350 + 35);
          $(this).css('color', 'hsl(' + hue + ', 80%, ' + lightness + '%)');
          if (numbers.length > 1) {
            return $('#report_legend').show('fast');
          }
        });
      }
    });
  };

}).call(this);

//# sourceMappingURL=build_total_report.map
