/**
 * SPAO Buoy — Google Apps Script Webhook
 *
 * Receives RockBLOCK POST requests, decodes telemetry packets,
 * and appends decoded rows to per-IMEI worksheets.
 *
 * NOTE: This file is for reference only and is deployed separately
 * via Google Apps Script (not part of the Streamlit app).
 */

// ── Helpers ──────────────────────────────────────────────────────

function readUint16(bytes, offset) {
  return (bytes[offset] << 8) | bytes[offset + 1];
}

function readInt16(bytes, offset) {
  var val = readUint16(bytes, offset);
  return val >= 0x8000 ? val - 0x10000 : val;
}

function readInt32(bytes, offset) {
  var val = (bytes[offset] << 24) | (bytes[offset + 1] << 16) |
            (bytes[offset + 2] << 8) | bytes[offset + 3];
  return val;
}

function hexToBytes(hex) {
  var bytes = [];
  for (var i = 0; i < hex.length; i += 2) {
    bytes.push(parseInt(hex.substr(i, 2), 16));
  }
  return bytes;
}

function crc8(bytes, len) {
  var crc = 0;
  for (var i = 0; i < len; i++) {
    var extract = bytes[i];
    for (var j = 0; j < 8; j++) {
      var s = (crc ^ extract) & 0x01;
      crc >>= 1;
      if (s) crc ^= 0x8C;
      extract >>= 1;
    }
  }
  return crc;
}

// ── Decoders ─────────────────────────────────────────────────────

function decodeFY25(bytes) {
  // FY25: TENG current is stored as mA × 1000 (µA), divide to get mA
  var tengCurr = readUint16(bytes, 0) / 1000.0;

  // Previous session fields (bytes 2-14) — FY25 Bering Sea deployment
  var prev2ndRB       = readUint16(bytes, 2) / 10.0;   // ×100ms → s; 0 if no retry
  var prevGPS         = readUint16(bytes, 4) / 10.0;   // ×100ms → s
  var prevSCapInit    = readUint16(bytes, 6) / 1000.0;  // mV → V
  var prevSCap1stF    = readUint16(bytes, 8) / 1000.0;  // mV → V; 0 if no 1st charge
  // bytes 10-11: unused (always 0x0000)
  var prevSCapAfterTX = readUint16(bytes, 12) / 1000.0; // mV → V
  // byte 14: unused (always 0x00)

  // Current session
  var battery  = readUint16(bytes, 15) / 1000.0;
  var lat      = readInt32(bytes, 17)  / 1e7;
  var lon      = readInt32(bytes, 21)  / 1e7;
  var gpsTime  = readUint16(bytes, 25) * 100 / 1000;
  var pressure = readUint16(bytes, 27) / 1000.0;
  var intTemp  = readInt16(bytes, 29)  / 100.0;
  var humidity = readUint16(bytes, 31) / 10.0;
  var sst      = readInt16(bytes, 33)  / 1000.0;
  var superCap = readUint16(bytes, 35) / 1000.0;

  var crcByte = bytes[37];
  var crcCalc = crc8(bytes, 37);
  var crcOk   = (crcByte === crcCalc) || (crcByte === 0x00);

  return {
    version: "FY25", crcOk: crcOk,
    tengCurr: tengCurr,
    prev2ndRB: prev2ndRB, prevGPS: prevGPS,
    prevSCapInit: prevSCapInit, prevSCap1stF: prevSCap1stF,
    prevSCapAfterTX: prevSCapAfterTX,
    battery: battery, lat: lat, lon: lon, gpsTime: gpsTime,
    pressure: pressure, intTemp: intTemp,
    humidity: humidity, sst: sst, superCap: superCap
  };
}

function decodeFY26v3(bytes) {
  var tengCurr    = readUint16(bytes, 0);
  var prev1stRB   = readUint16(bytes, 2) / 10.0;
  var prev2ndRB   = readUint16(bytes, 4) / 10.0;
  var prevGPS     = readUint16(bytes, 6) / 10.0;
  var prevTengAvg = readUint16(bytes, 8);
  var prevTengMax = readUint16(bytes, 10);
  var prevBatt    = readUint16(bytes, 12) / 1000.0;
  var prevEnd     = readUint16(bytes, 14);
  var battery     = readUint16(bytes, 16) / 1000.0;
  var lat         = readInt32(bytes, 18)  / 1e7;
  var lon         = readInt32(bytes, 22)  / 1e7;
  var gpsTime     = readUint16(bytes, 26) / 10.0;
  var pressure    = readUint16(bytes, 28) / 1000.0;
  var intTemp     = readInt16(bytes, 30)  / 100.0;
  var humidity    = readUint16(bytes, 32) / 10.0;
  var sst         = readInt16(bytes, 34)  / 1000.0;

  var crcOk = (bytes[36] === crc8(bytes, 36));

  return {
    version: "FY26(v3)", crcOk: crcOk,
    tengCurr: tengCurr, prev1stRB: prev1stRB, prev2ndRB: prev2ndRB,
    prevGPS: prevGPS, prevTengAvg: prevTengAvg, prevTengMax: prevTengMax,
    prevBatt: prevBatt, prevEnd: prevEnd,
    battery: battery, lat: lat, lon: lon, gpsTime: gpsTime,
    pressure: pressure, intTemp: intTemp, humidity: humidity, sst: sst
  };
}

/**
 * Decode V6.4 45-byte packet.
 * Changes from FY26: TENG Avg is best 1-min sliding window (scale /100),
 * Prev TENG Avg/Max scale /100, added Prev Oper Time at offset 22,
 * all subsequent fields shifted +2 bytes.
 */
function decodeV64(bytes) {
  var tengCurr     = readUint16(bytes, 0) / 100.0;  // best 1-min window
  var prev1stRB    = readUint16(bytes, 2) / 10.0;
  var prev2ndRB    = readUint16(bytes, 4) / 10.0;
  var prevGPS      = readUint16(bytes, 6) / 10.0;
  var prevTengAvg  = readUint16(bytes, 8) / 100.0;
  var prevTengMax  = readUint16(bytes, 10) / 100.0;
  // Prev TENG Time (12-17): YY,MM,DD,HH,mm,SS
  var prevTengTime = "20" + pad2(bytes[12]) + "-" + pad2(bytes[13]) + "-" + pad2(bytes[14]) +
                     " " + pad2(bytes[15]) + ":" + pad2(bytes[16]) + ":" + pad2(bytes[17]);
  var prevBatt     = readUint16(bytes, 18) / 1000.0;
  var prevEnd      = readUint16(bytes, 20);
  var prevOperTime = readUint16(bytes, 22);  // NEW in V6.4
  var battery      = readUint16(bytes, 24) / 1000.0;
  var lat          = readInt32(bytes, 26)  / 1e7;
  var lon          = readInt32(bytes, 30)  / 1e7;
  var gpsTime      = readUint16(bytes, 34) / 10.0;
  var pressure     = readUint16(bytes, 36) / 1000.0;
  var intTemp      = readInt16(bytes, 38)  / 100.0;
  var humidity     = readUint16(bytes, 40) / 10.0;
  var sst          = readInt16(bytes, 42)  / 1000.0;

  var crcOk = (bytes[44] === crc8(bytes, 44));

  return {
    version: "V6.4", crcOk: crcOk,
    tengCurr: tengCurr, prev1stRB: prev1stRB, prev2ndRB: prev2ndRB,
    prevGPS: prevGPS, prevTengAvg: prevTengAvg, prevTengMax: prevTengMax,
    prevTengTime: prevTengTime, prevBatt: prevBatt, prevEnd: prevEnd,
    prevOperTime: prevOperTime,
    battery: battery, lat: lat, lon: lon, gpsTime: gpsTime,
    pressure: pressure, intTemp: intTemp, humidity: humidity, sst: sst
  };
}

/**
 * Decode V6.4+EC 49-byte packet (V6.4 + SSS/conductivity).
 */
function decodeV64EC(bytes) {
  var base = decodeV64(bytes);  // reuse V6.4 field parsing (CRC will be wrong but we recalc)
  var salinity     = readUint16(bytes, 44) / 1000.0;
  var ec           = readUint16(bytes, 46) / 100.0;
  var crcOk = (bytes[48] === crc8(bytes, 48));

  base.version = "V6.4+EC";
  base.crcOk = crcOk;
  base.salinity = salinity;
  base.ec = ec;
  return base;
}

function pad2(n) {
  return n < 10 ? "0" + n : "" + n;
}

// ── Webhook Entry Point ──────────────────────────────────────────

function doPost(e) {
  try {
    var params = e.parameter;
    var imei   = params.imei || "unknown";
    var data   = params.data || "";

    var bytes  = hexToBytes(data);
    var len    = bytes.length;
    var result;

    if (len === 45) {
      result = decodeV64(bytes);
    } else if (len === 49) {
      result = decodeV64EC(bytes);
    } else if (len === 38 || len === 41) {
      result = decodeFY25(bytes);
    } else if (len === 37) {
      result = decodeFY26v3(bytes);
    } else {
      result = { version: "unknown", crcOk: false };
    }

    // Append to per-IMEI worksheet
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var ws;
    try {
      ws = ss.getSheetByName(imei);
    } catch (_) {
      ws = null;
    }
    if (!ws) {
      ws = ss.insertSheet(imei);
      ws.appendRow([
        "Receive Time", "Transmit Time", "IMEI", "MOMSN",
        "Raw Hex", "Packet Ver", "Bytes", "CRC Valid",
        "TENG Current Avg", "Prev Oper Time", "Battery",
        "GPS Latitude", "GPS Longitude", "GPS Acq Time",
        "Pressure", "Internal Temp", "Humidity", "SST",
        "Salinity", "EC Conductivity"
      ]);
    }

    ws.appendRow([
      new Date().toISOString(),
      params.transmit_time || "",
      imei,
      params.momsn || "",
      data,
      result.version,
      len,
      result.crcOk,
      result.tengCurr    || "",
      result.prevOperTime || "",
      result.battery     || "",
      result.lat         || "",
      result.lon         || "",
      result.gpsTime     || "",
      result.pressure    || "",
      result.intTemp     || "",
      result.humidity    || "",
      result.sst         || "",
      result.salinity    || "",
      result.ec          || ""
    ]);

    return ContentService.createTextOutput("OK");
  } catch (err) {
    // Log error to _errors tab
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var errSheet = ss.getSheetByName("_errors") || ss.insertSheet("_errors");
    errSheet.appendRow([new Date().toISOString(), err.toString()]);
    return ContentService.createTextOutput("ERROR: " + err);
  }
}
