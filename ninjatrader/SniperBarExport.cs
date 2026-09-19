// SniperBarExport — NinjaTrader 8 indicator. Writes every bar the chart has
// loaded to a CSV the Discord Sniper mirror can read (bars/<ROOT>_1m_<first>_<last>.csv,
// columns ts_event,symbol,open,high,low,close,volume — the same shape as the
// Databento files). One year of 1-minute ES/NQ for free, off the NinjaTrader
// data you already pay for.
//
// USE: open a chart of ES 12-26 (and one of NQ 12-26), 1 Minute, right-click >
// Data Series > "Days to load" = 365 (or "Load data based on: Days", 365), OK.
// Wait for the chart to finish loading. Indicators > SniperBarExport > OK.
// It writes the file once, when the historical bars are done, and prints the
// path in the Output window (New > NinjaScript Output). Remove it afterwards.
// Note: NinjaTrader stitches contracts with "Merge policy" (Data Series >
// Merge Policy: MergeBackAdjusted / MergeNonBackAdjusted). Use
// MergeNonBackAdjusted so the prices are the real prints of each month.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class SniperBarExport : Indicator
    {
        private bool written = false;

        [NinjaScriptProperty]
        [Display(Name = "Folder", Description = "The discord-sniper\\bars folder", Order = 1, GroupName = "Parameters")]
        public string Folder { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "SniperBarExport";
                Description = "Writes this chart's loaded bars to a CSV for the Discord Sniper futures mirror.";
                Calculate   = Calculate.OnBarClose;
                IsOverlay   = true;
                Folder      = @"C:\Users\Hulk\Desktop\discord-sniper\bars";
            }
            else if (State == State.Transition)
            {
                // Historical bars are all in; write once before real-time begins.
                if (!written) { written = true; Export(); }
            }
        }

        protected override void OnBarUpdate() { }

        private void Export()
        {
            try
            {
                if (Bars == null || Bars.Count == 0) { Print("SniperBarExport: no bars loaded"); return; }
                string root = Instrument.MasterInstrument.Name.ToUpperInvariant();
                var sb = new StringBuilder();
                sb.AppendLine("ts_event,symbol,open,high,low,close,volume");
                DateTime first = DateTime.MaxValue, last = DateTime.MinValue;
                for (int i = 0; i < Bars.Count; i++)
                {
                    // Bars.GetTime is the bar CLOSE time in the chart's zone; the
                    // mirror wants the bar OPEN time in UTC, like Databento.
                    DateTime closeLocal = Bars.GetTime(i);
                    DateTime openUtc = closeLocal.AddMinutes(-1).ToUniversalTime();
                    if (openUtc < first) first = openUtc;
                    if (openUtc > last) last = openUtc;
                    sb.Append(openUtc.ToString("yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture)).Append("+00:00,")
                      .Append(root).Append(".c.0,")
                      .Append(Bars.GetOpen(i).ToString(CultureInfo.InvariantCulture)).Append(',')
                      .Append(Bars.GetHigh(i).ToString(CultureInfo.InvariantCulture)).Append(',')
                      .Append(Bars.GetLow(i).ToString(CultureInfo.InvariantCulture)).Append(',')
                      .Append(Bars.GetClose(i).ToString(CultureInfo.InvariantCulture)).Append(',')
                      .Append(Bars.GetVolume(i).ToString(CultureInfo.InvariantCulture)).AppendLine();
                }
                if (!Directory.Exists(Folder)) Directory.CreateDirectory(Folder);
                string path = Path.Combine(Folder, root + "_1m_" + first.ToString("yyyy-MM-dd") + "_" + last.ToString("yyyy-MM-dd") + ".csv");
                File.WriteAllText(path, sb.ToString());
                Print("SniperBarExport: wrote " + Bars.Count + " bars to " + path);
            }
            catch (Exception ex) { Print("SniperBarExport failed: " + ex.Message); }
        }
    }
}
