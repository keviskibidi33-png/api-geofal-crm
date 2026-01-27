      {/* Modal: Cargar Plantilla - VERSIÓN DETALLADA CON ACORDEÓN */}
      {showPlantillasModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-slate-200">
              <h2 className="text-xl font-semibold text-slate-900 mb-2">Cargar Plantilla</h2>
              <p className="text-sm text-slate-600 mb-3">Selecciona una plantilla para aplicar su configuración completa</p>
              
              {/* Buscador de plantillas */}
              <div className="relative">
                <input
                  type="text"
                  value={plantillaSearch}
                  onChange={(e) => setPlantillaSearch(e.target.value)}
                  placeholder="Buscar por nombre, descripción o código de ensayo..."
                  className="w-full px-4 py-2 pl-10 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
                <svg className="absolute left-3 top-2.5 h-5 w-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
            </div>
            
            <div className="flex-1 overflow-y-auto">
              {loadingPlantillas ? (
                <div className="text-center py-12 text-slate-500">
                  <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-3"></div>
                  <p>Cargando plantillas...</p>
                </div>
              ) : plantillas.filter(p => {
                const searchLower = plantillaSearch.toLowerCase();
                const items = Array.isArray(p.items_json) ? p.items_json : JSON.parse(p.items_json || '[]');
                const itemsText = items.map((item: any) => `${item.codigo} ${item.descripcion}`).join(' ').toLowerCase();
                return p.nombre.toLowerCase().includes(searchLower) ||
                       (p.descripcion || '').toLowerCase().includes(searchLower) ||
                       itemsText.includes(searchLower);
              }).length === 0 ? (
                <div className="text-center py-12">
                  <FileText className="h-16 w-16 text-slate-300 mx-auto mb-4" />
                  <p className="text-slate-500 mb-1 font-medium">
                    {plantillaSearch ? 'No se encontraron plantillas' : 'No hay plantillas guardadas'}
                  </p>
                  <p className="text-sm text-slate-400">
                    {plantillaSearch ? 'Intenta con otros términos de búsqueda' : 'Crea una cotización y guárdala como plantilla'}
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-slate-200">
                  {plantillas.filter(p => {
                    const searchLower = plantillaSearch.toLowerCase();
                    const items = Array.isArray(p.items_json) ? p.items_json : JSON.parse(p.items_json || '[]');
                    const itemsText = items.map((item: any) => `${item.codigo} ${item.descripcion}`).join(' ').toLowerCase();
                    return p.nombre.toLowerCase().includes(searchLower) ||
                           (p.descripcion || '').toLowerCase().includes(searchLower) ||
                           itemsText.includes(searchLower);
                  }).map((plantilla) => {
                    const items = Array.isArray(plantilla.items_json) 
                      ? plantilla.items_json 
                      : JSON.parse(plantilla.items_json || '[]');
                    const condicionesPlantilla = condiciones.filter(c => plantilla.condiciones_ids?.includes(c.id));
                    const isExpanded = expandedPlantilla === plantilla.id;

                    return (
                      <div
                        key={plantilla.id}
                        className="hover:bg-slate-50 transition-colors"
                      >
                        {/* Header de la plantilla */}
                        <div className="px-6 py-4">
                          <div className="flex items-start gap-4">
                            {/* Botón expandir/contraer */}
                            <button
                              onClick={() => setExpandedPlantilla(isExpanded ? null : plantilla.id)}
                              className="flex-shrink-0 mt-1 p-1 hover:bg-slate-200 rounded transition-colors"
                            >
                              <svg 
                                className={`h-5 w-5 text-slate-600 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                                fill="none" 
                                stroke="currentColor" 
                                viewBox="0 0 24 24"
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                              </svg>
                            </button>

                            {/* Contenido principal */}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-start justify-between gap-4 mb-2">
                                <div className="flex-1">
                                  <h3 className="text-lg font-semibold text-slate-900 mb-1">{plantilla.nombre}</h3>
                                  {plantilla.descripcion && (
                                    <p className="text-sm text-slate-600">{plantilla.descripcion}</p>
                                  )}
                                </div>
                                <div className="flex items-center gap-2 flex-shrink-0">
                                  <span className="text-xs bg-blue-100 text-blue-700 px-3 py-1 rounded-full font-semibold">
                                    {plantilla.veces_usada || 0} usos
                                  </span>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setPlantillaToDelete(plantilla);
                                      setShowDeletePlantillaModal(true);
                                    }}
                                    className="p-2 hover:bg-red-50 rounded-lg text-red-600 hover:text-red-700 transition-colors"
                                    title="Eliminar plantilla"
                                  >
                                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                    </svg>
                                  </button>
                                </div>
                              </div>

                              {/* Resumen compacto */}
                              <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600">
                                <span className="flex items-center gap-1.5 font-medium">
                                  <FileText className="h-4 w-4 text-blue-500" />
                                  {items.length} ensayo{items.length !== 1 ? 's' : ''}
                                </span>
                                {condicionesPlantilla.length > 0 && (
                                  <span className="flex items-center gap-1.5">
                                    <svg className="h-4 w-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    </svg>
                                    {condicionesPlantilla.length} condición{condicionesPlantilla.length !== 1 ? 'es' : ''}
                                  </span>
                                )}
                                {plantilla.plazo_dias && (
                                  <span className="flex items-center gap-1.5">
                                    📅 {plantilla.plazo_dias} días
                                  </span>
                                )}
                                {plantilla.condicion_pago && (
                                  <span className="flex items-center gap-1.5">
                                    💳 {plantilla.condicion_pago}
                                  </span>
                                )}
                                <span className="text-xs text-slate-400 ml-auto">
                                  Creada: {new Date(plantilla.created_at).toLocaleDateString('es-PE', { 
                                    day: '2-digit', 
                                    month: 'short', 
                                    year: 'numeric' 
                                  })}
                                </span>
                              </div>

                              {/* Detalles expandidos */}
                              {isExpanded && (
                                <div className="mt-4 space-y-4 bg-slate-50 rounded-lg p-4 border border-slate-200">
                                  {/* Lista detallada de ensayos */}
                                  <div>
                                    <h4 className="text-sm font-semibold text-slate-900 mb-2 flex items-center gap-2">
                                      <FileText className="h-4 w-4 text-blue-500" />
                                      Ensayos incluidos ({items.length})
                                    </h4>
                                    <div className="bg-white rounded border border-slate-200 divide-y divide-slate-100 max-h-60 overflow-y-auto">
                                      {items.map((item: any, idx: number) => (
                                        <div key={idx} className="px-3 py-2 hover:bg-blue-50 transition-colors">
                                          <div className="flex items-start justify-between gap-3">
                                            <div className="flex-1 min-w-0">
                                              <div className="flex items-center gap-2 mb-1">
                                                <span className="text-xs font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                                                  {item.codigo}
                                                </span>
                                                <span className="text-sm font-medium text-slate-900 truncate">
                                                  {item.descripcion}
                                                </span>
                                              </div>
                                              <div className="flex items-center gap-3 text-xs text-slate-600">
                                                <span>Categoría: <span className="font-medium">{item.categoria}</span></span>
                                                <span>Cantidad: <span className="font-medium">{item.cantidad}</span></span>
                                                <span>P.U.: <span className="font-medium">S/ {item.precio_unitario?.toFixed(2)}</span></span>
                                              </div>
                                            </div>
                                            <div className="text-right flex-shrink-0">
                                              <div className="text-sm font-semibold text-slate-900">
                                                S/ {(item.cantidad * item.precio_unitario).toFixed(2)}
                                              </div>
                                            </div>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>

                                  {/* Lista detallada de condiciones */}
                                  {condicionesPlantilla.length > 0 && (
                                    <div>
                                      <h4 className="text-sm font-semibold text-slate-900 mb-2 flex items-center gap-2">
                                        <svg className="h-4 w-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                        </svg>
                                        Condiciones específicas ({condicionesPlantilla.length})
                                      </h4>
                                      <div className="bg-white rounded border border-slate-200 divide-y divide-slate-100 max-h-60 overflow-y-auto">
                                        {condicionesPlantilla.map((condicion, idx) => (
                                          <div key={condicion.id} className="px-3 py-2.5">
                                            <div className="flex items-start gap-2">
                                              <span className="flex-shrink-0 mt-0.5 h-5 w-5 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-xs font-semibold">
                                                {idx + 1}
                                              </span>
                                              <div className="flex-1">
                                                <p className="text-sm text-slate-700 leading-relaxed">{condicion.texto}</p>
                                                {condicion.categoria && (
                                                  <span className="inline-block mt-1 text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                                                    {condicion.categoria}
                                                  </span>
                                                )}
                                              </div>
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}

                                  {/* Botón para aplicar plantilla */}
                                  <Button
                                    onClick={() => handleLoadPlantilla(plantilla.id)}
                                    className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                                  >
                                    <svg className="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                    </svg>
                                    Aplicar esta plantilla
                                  </Button>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="px-6 py-4 border-t border-slate-200 flex justify-between items-center bg-slate-50">
              <p className="text-sm text-slate-600">
                {plantillas.filter(p => {
                  const searchLower = plantillaSearch.toLowerCase();
                  const items = Array.isArray(p.items_json) ? p.items_json : JSON.parse(p.items_json || '[]');
                  const itemsText = items.map((item: any) => `${item.codigo} ${item.descripcion}`).join(' ').toLowerCase();
                  return p.nombre.toLowerCase().includes(searchLower) ||
                         (p.descripcion || '').toLowerCase().includes(searchLower) ||
                         itemsText.includes(searchLower);
                }).length} plantilla(s) encontrada(s)
              </p>
              <Button variant="outline" onClick={() => {
                setShowPlantillasModal(false);
                setPlantillaSearch('');
                setExpandedPlantilla(null);
              }}>
                Cerrar
              </Button>
            </div>
          </div>
        </div>
      )}
