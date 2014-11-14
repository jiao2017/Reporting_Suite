//@ sourceMappingURL=build_report.map
// Generated by CoffeeScript 1.6.1
(function() {
  var extend, merge, metric, preprocessReport, readJson, recoverOrderFromCookies, report, section, showPlotWithInfo, totalReportData;

  showPlotWithInfo = function(info) {
    var newColors, newSeries;
    newSeries = [];
    newColors = [];
    return $('#legend-placeholder').find('input:checked'.each(function() {
      var i, number, series, _i, _ref;
      number = $(this).attr('name');
      if (number && info.series && info.series.length > 0) {
        for (i = _i = i, _ref = info.series.length; i <= _ref ? _i < _ref : _i > _ref; i = i <= _ref ? ++_i : --_i) {
          series = info.series[i];
          if (series.number !== number) {
            break;
          }
        }
        if (i <= info.series.length) {
          newSeries.push(series);
          newColors.push(series.color);
        } else {
          if (window.console != null) {
            console.log('no series with number ' + number);
          }
        }
      }
      if (newSeries.length === 0) {
        newSeries.push({
          data: []
        });
        newColors.push('#FFF');
      }
      return info.showWithData(newSeries, newColors);
    }));
  };

  recoverOrderFromCookies = function(report_name) {
    var columnOrder, fail, orderString, val, _i, _len, _ref;
    if (!navigator.cookieEnabled) {
      return null;
    }
    orderString = readCookie(report_name + '_order');
    if (!orderString) {
      return null;
    }
    columnOrder = [];
    fail = false;
    _ref = orderString.split(' ');
    for (_i = 0, _len = _ref.length; _i < _len; _i++) {
      val = _ref[_i];
      val = parseInt(val);
      if (isNaN(val)) {
        fail = true;
      } else {
        columnOrder.push(val);
      }
    }
    if (fail) {
      return null;
    }
    return columnOrder;
  };

  readJson = function(what) {
    result;
    var result;
    try {
      result = JSON.parse($('#' + what + '-json').html());
    } catch (e) {
      result = null;
    }
    return result;
  };

  totalReportData = {
    date: null,
    report: null
  };

  report = {
    name: '',
    order: null,
    sample_reports: [],
    metric_storage: {
      general_section: {
        name: '',
        metrics: []
      },
      sections: []
    }
  };

  section = {
    name: '',
    title: '',
    metrics: [],
    metrics_by_name: {}
  };

  metric = {
    name: '',
    short_name: '',
    description: '',
    quality: '',
    common: true,
    unit: ''
  };

  extend = function(object, properties) {
    var key, val;
    for (key in properties) {
      val = properties[key];
      object[key] = val;
    }
    return object;
  };

  merge = function(options, overrides) {
    return extend(extend({}, options), overrides);
  };

  preprocessReport = function(report) {
    var all_metrics_by_name, m, rec, s, sample_report, _i, _j, _k, _l, _len, _len1, _len2, _len3, _len4, _len5, _m, _n, _ref, _ref1, _ref2, _ref3, _ref4, _ref5;
    all_metrics_by_name = {};
    _ref = report.metric_storage.general_section.metrics;
    for (_i = 0, _len = _ref.length; _i < _len; _i++) {
      m = _ref[_i];
      report.metric_storage.general_section.metrics_by_name[m.name] = m;
    }
    extend(all_metrics_by_name, report.metric_storage.general_section.metrics_by_name);
    _ref1 = report.metric_storage.sections;
    for (_j = 0, _len1 = _ref1.length; _j < _len1; _j++) {
      s = _ref1[_j];
      _ref2 = s.metrics;
      for (_k = 0, _len2 = _ref2.length; _k < _len2; _k++) {
        m = _ref2[_k];
        s.metrics_by_name[m.name] = m;
      }
      extend(all_metrics_by_name, s.metrics_by_name);
    }
    if (report.hasOwnProperty('sample_reports')) {
      _ref3 = report.sample_reports;
      for (_l = 0, _len3 = _ref3.length; _l < _len3; _l++) {
        sample_report = _ref3[_l];
        sample_report.metric_storage = report.metric_storage;
        _ref4 = sample_report.records;
        for (_m = 0, _len4 = _ref4.length; _m < _len4; _m++) {
          rec = _ref4[_m];
          rec.metric = all_metrics_by_name[rec.metric.name];
        }
      }
    } else {
      _ref5 = report.records;
      for (_n = 0, _len5 = _ref5.length; _n < _len5; _n++) {
        rec = _ref5[_n];
        rec.metric = all_metrics_by_name[rec.metric.name];
      }
    }
    return report;
  };

  reporting.buildReport = function() {
    var columnNames, columnOrder, common_metrics_by_name, general_records, m, plot, plots_html, rec, records, _i, _j, _k, _len, _len1, _ref, _ref1, _ref2, _results;
    totalReportData = readJson('total-report');
    if (!totalReportData) {
      if (window.console != null) {
        console.log("Error: cannot read #total-report-json");
      }
      return 1;
    }
    report = preprocessReport(totalReportData.report);
    $('#report_date').html('<p>' + totalReportData.date + '</p>');
    common_metrics_by_name = report.metric_storage.general_section.metrics_by_name;
    records = report.hasOwnProperty('sample_reports') ? report.sample_reports[0].records : report.records;
    general_records = (function() {
      var _i, _len, _results;
      _results = [];
      for (_i = 0, _len = records.length; _i < _len; _i++) {
        rec = records[_i];
        if (rec.metric.name in common_metrics_by_name) {
          _results.push(rec);
        }
      }
      return _results;
    })();
    reporting.buildCommonRecords(general_records);
    _ref = report.metric_storage.sections;
    for (_i = 0, _len = _ref.length; _i < _len; _i++) {
      section = _ref[_i];
      columnNames = (function() {
        var _j, _len1, _ref1, _results;
        _ref1 = section.metrics;
        _results = [];
        for (_j = 0, _len1 = _ref1.length; _j < _len1; _j++) {
          m = _ref1[_j];
          _results.push(m.name);
        }
        return _results;
      })();
      columnOrder = (recoverOrderFromCookies(section.name)) || report.order || (function() {
        _results = [];
        for (var _j = 0, _ref1 = columnNames.length; 0 <= _ref1 ? _j < _ref1 : _j > _ref1; 0 <= _ref1 ? _j++ : _j--){ _results.push(_j); }
        return _results;
      }).apply(this);
      reporting.buildTotalReport(report, section, columnOrder);
      if (report.hasOwnProperty('plots')) {
        plots_html = "";
        _ref2 = report.plots;
        for (_k = 0, _len1 = _ref2.length; _k < _len1; _k++) {
          plot = _ref2[_k];
          plots_html += "<img src=\"" + plot + "\"/>";
        }
        $('#plot').html(plots_html);
      }
    }
    return 0;
  };

}).call(this);
