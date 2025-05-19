#include <stdint.h>


/**
 * [CTXT]
 *  [FRAM]
 *    [VM0B]
 *      [RGBA] (stroke background)
 *      ...
 *      [RGBA] (stroke background)
 *      
 *      [RGBA] (stroke)
 *      ...
 *      [RGBA] (stroke)
 *      
*       [RGBA] (fill)
 *      ...
 *      [RGBA] (fill)
 *      
 *      [SUBP]
 *        [QUAD]
 *        ...
 *        [QUAD]
 *      [SUBP]
 *      
 *      ...
 *      [SUBP]
 *      
 *    [VMOB]
 *    ...
 *    [VMOB]
 *   [FRAM]
 *   ...
 *   [FRAM]
 *
 *
 *
 *
 */

#pragma pack(push, 1)

typedef struct {
  char magic[4]; /** CTXT **/
  uint32_t version;
  uint32_t pixelWidth, pixelHeight;
  float frameWidth, frameHeight;
} FileHeader;

typedef struct {
  char magic[4]; /** FRAM **/
  uint32_t VMOCount;
} FrameHeader;

typedef struct {
  char magic[4]; /** VMOB **/

  uint32_t Id;

  /** Style **/
  float strokeWidthBackground;
  float strokeWidth;
  
  uint32_t strokeRGBAsBackgroundCount;
  uint32_t strokeRGBAsCount;

  uint32_t fillRGBAsCount;

  float gradientX0, gradientY0;
  float gradientX1, gradientY1;

  /** Subpaths **/
  uint32_t subpathCount;
  
} VMO;

typedef struct {
  char magic[4]; /** RGBA **/
  float rgba[4];
} RGBA;

typedef struct {
  char magic[4]; /** SUBP **/
  float x, y;
  uint32_t quadCount;
} Subpath;

typedef struct {
  char magic[4]; /** QUAD **/
  float x1, y1;
  float x2, y2;
  float x3, y3;
} Quad;

int main() {
  
}