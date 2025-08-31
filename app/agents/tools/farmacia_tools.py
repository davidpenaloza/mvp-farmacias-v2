#!/usr/bin/env python3
"""
Search Farmacias Tool for AI Agent
Searches for pharmacies using existing infrastructure
"""

import logging
from typing import Dict, Any, List, Optional
from app.agents.tools.base_tool import BaseTool
from app.database import PharmacyDatabase
from app.cache.redis_client import get_redis_client

logger = logging.getLogger(__name__)

class SearchFarmaciasTool(BaseTool):
    """
    Tool for searching pharmacies by commune, duty status, and other criteria
    """
    
    def __init__(self):
        super().__init__(
            name="search_farmacias",
            description="Busca farmacias por comuna, estado de turno y otros criterios. Utiliza la base de datos actualizada de farmacias en Chile."
        )
        self.db = PharmacyDatabase()
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute pharmacy search
        
        Args:
            comuna (str): Nombre de la comuna para buscar farmacias
            turno (bool, optional): Si buscar solo farmacias de turno (True) o todas (False)
            limite (int, optional): Número máximo de resultados (default: 10)
            incluir_cerradas (bool, optional): Si incluir farmacias cerradas (default: False)
            
        Returns:
            Dictionary with search results
        """
        comuna = kwargs.get("comuna", "").strip()
        turno = kwargs.get("turno", False)
        limite = kwargs.get("limite", 10)
        incluir_cerradas = kwargs.get("incluir_cerradas", False)
        
        # Validate inputs
        if not comuna:
            return {
                "error": "Se requiere especificar una comuna para la búsqueda",
                "farmacias": [],
                "total": 0
            }
        
        try:
            # Use existing database methods
            if turno:
                # Search for duty pharmacies in specific commune
                farmacias_filtradas = self.db.find_by_comuna(comuna, only_open=True)
            else:
                # Search all pharmacies in commune
                farmacias_filtradas = self.db.find_by_comuna(comuna, only_open=False)
            
            # Apply additional filters
            if not incluir_cerradas:
                # Filter out closed pharmacies using database method
                farmacias_filtradas = [
                    farmacia for farmacia in farmacias_filtradas
                    if self.db.is_pharmacy_currently_open(farmacia)
                ]
            
            # Apply limit
            farmacias_resultado = farmacias_filtradas[:limite] if limite > 0 else farmacias_filtradas
            
            # Format results for agent
            farmacias_formateadas = []
            for farmacia in farmacias_resultado:
                farmacia_info = {
                    "nombre": farmacia.nombre,
                    "direccion": farmacia.direccion,
                    "comuna": farmacia.comuna,
                    "telefono": farmacia.telefono or "Sin teléfono",
                    "horario": f"{farmacia.hora_apertura} - {farmacia.hora_cierre}" if farmacia.hora_apertura and farmacia.hora_cierre else "Sin información de horarios",
                    "turno": farmacia.es_turno,
                    "abierta": self.db.is_pharmacy_currently_open(farmacia),
                    "cadena": "Independiente"  # Could be enhanced with actual chain data
                }
                
                # Add coordinates if available
                if farmacia.lat and farmacia.lng and farmacia.lat != 0.0 and farmacia.lng != 0.0:
                    farmacia_info["ubicacion"] = {
                        "latitud": farmacia.lat,
                        "longitud": farmacia.lng
                    }
                
                farmacias_formateadas.append(farmacia_info)
            
            # Generate summary
            total_encontradas = len(farmacias_filtradas)
            mostradas = len(farmacias_formateadas)
            
            resumen = {
                "comuna_consultada": comuna,
                "solo_turno": turno,
                "total_encontradas": total_encontradas,
                "mostradas": mostradas,
                "incluye_cerradas": incluir_cerradas
            }
            
            return {
                "farmacias": farmacias_formateadas,
                "resumen": resumen,
                "total": total_encontradas,
                "mensaje": f"Se encontraron {total_encontradas} farmacias en {comuna}" + 
                          (f" (solo de turno)" if turno else "") + 
                          (f". Mostrando {mostradas} resultados." if total_encontradas > mostradas else ".")
            }
            
        except Exception as e:
            logger.error(f"❌ Error searching pharmacies: {e}")
            return {
                "error": f"Error al buscar farmacias: {str(e)}",
                "farmacias": [],
                "total": 0
            }
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Get JSON schema for search parameters
        """
        return {
            "type": "object",
            "properties": {
                "comuna": {
                    "type": "string",
                    "description": "Nombre de la comuna donde buscar farmacias (ej: 'Villa Alemana', 'Santiago', 'Valparaíso')"
                },
                "turno": {
                    "type": "boolean",
                    "description": "Si buscar solo farmacias de turno (true) o todas las farmacias (false)",
                    "default": False
                },
                "limite": {
                    "type": "integer",
                    "description": "Número máximo de farmacias a retornar",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10
                },
                "incluir_cerradas": {
                    "type": "boolean",
                    "description": "Si incluir farmacias que están cerradas en los resultados",
                    "default": False
                }
            },
            "required": ["comuna"]
        }


class SearchFarmaciasNearbyTool(BaseTool):
    """
    Tool for searching pharmacies by geographic coordinates (nearby search)
    """
    
    def __init__(self):
        super().__init__(
            name="search_farmacias_nearby",
            description="Busca farmacias cercanas a unas coordenadas geográficas específicas. Utiliza latitud y longitud para encontrar las farmacias más cercanas."
        )
        self.db = PharmacyDatabase()
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute nearby pharmacy search by coordinates
        
        Args:
            latitud (float): Latitud de la ubicación
            longitud (float): Longitud de la ubicación  
            radio_km (float, optional): Radio de búsqueda en kilómetros (default: 5.0)
            solo_abiertas (bool, optional): Solo farmacias abiertas (default: True)
            limite (int, optional): Número máximo de resultados (default: 10)
            
        Returns:
            Dictionary with search results
        """
        try:
            latitud = float(kwargs.get("latitud", 0))
            longitud = float(kwargs.get("longitud", 0))
            radio_km = float(kwargs.get("radio_km", 5.0))
            solo_abiertas = kwargs.get("solo_abiertas", True)
            limite = kwargs.get("limite", 10)
            
            # Validate coordinates
            if latitud == 0 or longitud == 0:
                return {
                    "success": False,
                    "error": "Se requieren coordenadas válidas (latitud y longitud)",
                    "data": {"farmacias": [], "total": 0}
                }
            
            # Search for nearby pharmacies
            if solo_abiertas:
                farmacias_cercanas = self.db.find_nearby_pharmacies_open_now(latitud, longitud, radio_km)
            else:
                farmacias_cercanas = self.db.find_nearby_pharmacies(latitud, longitud, radio_km, False)
            
            # Apply limit
            farmacias_resultado = farmacias_cercanas[:limite] if limite > 0 else farmacias_cercanas
            
            # Format results for agent
            farmacias_formateadas = []
            for farmacia in farmacias_resultado:
                farmacia_info = {
                    "nombre": farmacia.nombre,
                    "direccion": farmacia.direccion,
                    "comuna": farmacia.comuna,
                    "telefono": farmacia.telefono or "Sin teléfono",
                    "horario": f"{farmacia.hora_apertura} - {farmacia.hora_cierre}",
                    "turno": farmacia.es_turno,
                    "abierta": self.db.is_pharmacy_currently_open(farmacia),
                    "cadena": "Independiente",  # Default value
                    "ubicacion": {
                        "latitud": farmacia.lat,
                        "longitud": farmacia.lng
                    }
                }
                farmacias_formateadas.append(farmacia_info)
            
            # Determine message based on results
            if farmacias_formateadas:
                tipo_busqueda = "abiertas" if solo_abiertas else "en el área"
                mensaje = f"Se encontraron {len(farmacias_formateadas)} farmacias {tipo_busqueda} en un radio de {radio_km}km."
            else:
                tipo_busqueda = "abiertas" if solo_abiertas else ""
                mensaje = f"No se encontraron farmacias {tipo_busqueda} en un radio de {radio_km}km de tu ubicación."
            
            return {
                "success": True,
                "data": {
                    "farmacias": farmacias_formateadas,
                    "resumen": {
                        "latitud": latitud,
                        "longitud": longitud,
                        "radio_km": radio_km,
                        "solo_abiertas": solo_abiertas,
                        "total_encontradas": len(farmacias_formateadas),
                        "mostradas": len(farmacias_formateadas)
                    },
                    "total": len(farmacias_formateadas),
                    "mensaje": mensaje
                },
                "tool": "search_farmacias_nearby"
            }
            
        except Exception as e:
            logger.error(f"Error in SearchFarmaciasNearbyTool: {e}")
            return {
                "success": False,
                "error": f"Error en la búsqueda por coordenadas: {str(e)}",
                "data": {"farmacias": [], "total": 0}
            }
    
    def get_openai_function_definition(self) -> Dict[str, Any]:
        """Return OpenAI function definition for this tool"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitud": {
                            "type": "number",
                            "description": "Latitud de la ubicación para buscar farmacias cercanas"
                        },
                        "longitud": {
                            "type": "number", 
                            "description": "Longitud de la ubicación para buscar farmacias cercanas"
                        },
                        "radio_km": {
                            "type": "number",
                            "description": "Radio de búsqueda en kilómetros (default: 5.0)",
                            "default": 5.0
                        },
                        "solo_abiertas": {
                            "type": "boolean",
                            "description": "Si buscar solo farmacias abiertas/de turno (default: true)",
                            "default": True
                        },
                        "limite": {
                            "type": "integer",
                            "description": "Número máximo de resultados a retornar (default: 10)",
                            "default": 10
                        }
                    },
                    "required": ["latitud", "longitud"]
                }
            }
        }
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters"""
        return {
            "type": "object",
            "properties": {
                "latitud": {
                    "type": "number",
                    "description": "Latitud de la ubicación para buscar farmacias cercanas"
                },
                "longitud": {
                    "type": "number", 
                    "description": "Longitud de la ubicación para buscar farmacias cercanas"
                },
                "radio_km": {
                    "type": "number",
                    "description": "Radio de búsqueda en kilómetros (default: 5.0)",
                    "default": 5.0
                },
                "solo_abiertas": {
                    "type": "boolean",
                    "description": "Si buscar solo farmacias abiertas/de turno (default: true)",
                    "default": True
                },
                "limite": {
                    "type": "integer",
                    "description": "Número máximo de resultados a retornar (default: 10)",
                    "default": 10
                }
            },
            "required": ["latitud", "longitud"]
        }


class GetCommunesTool(BaseTool):
    """
    Tool for getting available communes with pharmacies
    """
    
    def __init__(self):
        super().__init__(
            name="get_communes",
            description="Obtiene la lista de comunas disponibles que tienen farmacias registradas en el sistema."
        )
        self.db = PharmacyDatabase()
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Get list of available communes
        
        Args:
            region (str, optional): Filtrar por región específica
            
        Returns:
            Dictionary with commune list
        """
        region_filter = kwargs.get("region", "").strip()
        
        try:
            # Get all communes from the database
            comunas_disponibles = self.db.get_all_communes()
            
            if region_filter:
                # Basic region filtering (would be improved with proper data)
                if region_filter.lower() in ["valparaiso", "valparaíso", "v region", "v región"]:
                    # Filter for Valparaíso region communes
                    comunas_valparaiso = [
                        "Villa Alemana", "Valparaíso", "Viña del Mar",
                        "Quilpué", "Concón", "Casablanca", "Limache", "Olmué"
                    ]
                    comunas_disponibles = [
                        comuna for comuna in comunas_disponibles 
                        if comuna in comunas_valparaiso
                    ]
                elif region_filter.lower() in ["santiago", "metropolitana", "rm"]:
                    # Filter for Santiago region communes  
                    comunas_santiago = [
                        "Santiago", "Las Condes", "Providencia", "Ñuñoa",
                        "La Florida", "Maipú", "Puente Alto", "San Bernardo", "La Pintana"
                    ]
                    comunas_disponibles = [
                        comuna for comuna in comunas_disponibles 
                        if comuna in comunas_santiago
                    ]
            
            return {
                "comunas": sorted(comunas_disponibles),
                "total": len(comunas_disponibles),
                "region": region_filter if region_filter else "Todas las regiones",
                "mensaje": f"Se encontraron {len(comunas_disponibles)} comunas disponibles" + 
                          (f" en {region_filter}" if region_filter else "")
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting communes: {e}")
            return {
                "error": f"Error al obtener comunas: {str(e)}",
                "comunas": [],
                "total": 0
            }
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        Get JSON schema for commune parameters
        """
        return {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Nombre de la región para filtrar comunas (opcional)",
                    "examples": ["Valparaíso", "Santiago", "Metropolitana"]
                }
            },
            "required": []
        }
