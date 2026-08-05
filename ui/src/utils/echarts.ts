import { LineChart } from "echarts/charts";
import {
  AxisPointerComponent,
  DataZoomSliderComponent,
  GraphicComponent,
  GridComponent,
  LegendScrollComponent,
  MarkAreaComponent,
  MarkLineComponent,
  ToolboxComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  AxisPointerComponent,
  DataZoomSliderComponent,
  GraphicComponent,
  GridComponent,
  LegendScrollComponent,
  MarkAreaComponent,
  MarkLineComponent,
  ToolboxComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export { echarts };
export type { EChartsType } from "echarts/core";
